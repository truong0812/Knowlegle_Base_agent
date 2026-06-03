"""Phase 4 tests for graph-backed learning paths."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from kb_agent.dashboard.server import create_app
from kb_agent.graph.hotpath import HotPathScore
from kb_agent.graph.storage import GraphStorage
from kb_agent.learning.api import LearningApi
from kb_agent.learning.planner import LearningPathPlanner
from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode


def _node(
    name: str,
    path: str,
    *,
    kind: SymbolKind = SymbolKind.FUNCTION,
    line_start: int = 1,
) -> SymbolNode:
    return SymbolNode(
        id=f"repo/{path}::{name}",
        name=name,
        kind=kind,
        language=Language.PYTHON,
        path=path,
        line_start=line_start,
        line_end=line_start + 10,
        signature=f"def {name}():",
    )


def _make_path_kb(tmp_path: Path, *, with_cycle: bool = False) -> Path:
    repo = tmp_path / "repo"
    kb = repo / ".kb"
    graph_dir = kb / "graph"
    kb.mkdir(parents=True)
    (kb / "manifest.json").write_text(
        json.dumps({
            "source_repo": str(repo),
            "stats": {"total_entries": 6},
            "created_at": "2026-06-02T10:00:00",
        }),
        encoding="utf-8",
    )

    nodes = [
        _node("create_app", "kb_agent/dashboard/server.py", kind=SymbolKind.FUNCTION),
        _node("LearningApi", "kb_agent/learning/api.py", kind=SymbolKind.CLASS, line_start=20),
        _node("QueryEngine", "kb_agent/query/engine.py", kind=SymbolKind.CLASS, line_start=30),
        _node("retrieve_context", "kb_agent/query/retrieval.py", line_start=40),
        _node("GraphBuilder", "kb_agent/graph/builder.py", kind=SymbolKind.CLASS, line_start=50),
        _node("SymbolNode", "kb_agent/models/graph.py", kind=SymbolKind.CLASS, line_start=60),
    ]
    edges = [
        SymbolEdge(source=nodes[0].id, target=nodes[1].id, kind=EdgeKind.CALLS),
        SymbolEdge(source=nodes[2].id, target=nodes[3].id, kind=EdgeKind.CALLS),
        SymbolEdge(source=nodes[4].id, target=nodes[5].id, kind=EdgeKind.USES_TYPE),
        SymbolEdge(source=nodes[1].id, target=nodes[2].id, kind=EdgeKind.IMPORTS),
    ]
    if with_cycle:
        edges.extend([
            SymbolEdge(source=nodes[3].id, target=nodes[4].id, kind=EdgeKind.CALLS),
            SymbolEdge(source=nodes[4].id, target=nodes[3].id, kind=EdgeKind.CALLS),
        ])

    storage = GraphStorage(graph_dir)
    storage.save(nodes, edges)
    storage.save_hotpath({
        nodes[1].id: HotPathScore(node_id=nodes[1].id, incoming_calls=3, hotness=1.0),
        nodes[3].id: HotPathScore(node_id=nodes[3].id, incoming_calls=2, hotness=0.7),
        nodes[4].id: HotPathScore(node_id=nodes[4].id, incoming_calls=1, hotness=0.4),
    })
    return kb


def test_dashboard_recommends_three_generated_paths(tmp_path: Path):
    kb = _make_path_kb(tmp_path)
    client = TestClient(create_app(kb))

    resp = client.get("/api/learning/dashboard")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["recommended_paths"]) >= 3
    assert [path["id"] for path in data["recommended_paths"][:3]] == [
        "architecture-overview",
        "query-and-retrieval",
        "knowledge-graph-construction",
    ]
    assert data["recommended_paths"][0]["lesson_count"] == 3
    assert (kb / "learning" / "paths.json").exists()


def test_path_detail_uses_graph_citations_and_persisted_progress(tmp_path: Path):
    kb = _make_path_kb(tmp_path)
    client = TestClient(create_app(kb))

    detail_resp = client.get("/api/learning/paths/query-and-retrieval")
    detail = detail_resp.json()

    assert detail_resp.status_code == 200
    assert detail["lessons"][0]["citations"][0]["path"].startswith("kb_agent/query/")
    assert detail["lessons"][0]["related_topics"]

    complete_resp = client.post("/api/learning/paths/query-and-retrieval/lessons/lesson-1/complete")
    assert complete_resp.status_code == 200
    assert complete_resp.json()["progress"]["completed_lesson_count"] == 1

    progress = client.get("/api/learning/progress").json()
    assert progress["completed_lessons"][0]["path_id"] == "query-and-retrieval"
    assert progress["last_visited_context"]["path_id"] == "query-and-retrieval"


def test_path_generation_reports_circular_dependency_warning(tmp_path: Path):
    kb = _make_path_kb(tmp_path, with_cycle=True)
    api = LearningApi(kb)

    detail = api.path_detail("knowledge-graph-construction")

    assert detail is not None
    assert "circular_dependency_detected" in {warning.code for warning in detail.warnings}


def test_path_cache_is_reused_without_regeneration(tmp_path: Path):
    kb = _make_path_kb(tmp_path)
    api = LearningApi(kb)
    first = api.paths()

    cache_path = kb / "learning" / "paths.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    cache["paths"][0]["title"] = "Cached Architecture Path"
    cache_path.write_text(json.dumps(cache), encoding="utf-8")

    fresh_api = LearningApi(kb)
    second = fresh_api.paths()

    assert first[0].id == "architecture-overview"
    assert second[0].title == "Cached Architecture Path"


def test_path_planner_cycle_detection_handles_deep_graph_iteratively():
    nodes = [
        _node(f"node_{index}", f"src/node_{index}.py", line_start=index + 1)
        for index in range(1200)
    ]
    edges = [
        SymbolEdge(source=nodes[index].id, target=nodes[index + 1].id, kind=EdgeKind.CALLS)
        for index in range(len(nodes) - 1)
    ]
    edges.append(SymbolEdge(source=nodes[-1].id, target=nodes[25].id, kind=EdgeKind.CALLS))

    planned = LearningPathPlanner(nodes, edges).generate()

    assert len(planned.paths) == 3
    assert "circular_dependency_detected" in {warning.code for warning in planned.warnings}
