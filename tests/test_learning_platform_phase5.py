"""Phase 5 tests for personalized learning recommendations."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from kb_agent.dashboard.server import create_app
from kb_agent.graph.hotpath import HotPathScore
from kb_agent.graph.storage import GraphStorage
from kb_agent.learning.models import LearningPathSummary, UserProgress
from kb_agent.learning.recommendations import LearningRecommendationEngine
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


def _make_recommendation_kb(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    kb = repo / ".kb"
    graph_dir = kb / "graph"
    kb.mkdir(parents=True)
    (kb / "manifest.json").write_text(
        json.dumps({
            "source_repo": str(repo),
            "stats": {"total_entries": 5},
            "created_at": "2026-06-03T09:00:00",
        }),
        encoding="utf-8",
    )

    dashboard = _node("create_app", "kb_agent/dashboard/server.py")
    api = _node("LearningApi", "kb_agent/learning/api.py", kind=SymbolKind.CLASS, line_start=20)
    planner = _node("QueryPlanner", "kb_agent/query/planner.py", kind=SymbolKind.CLASS, line_start=30)
    retrieve = _node("retrieve", "kb_agent/query/retrieval.py", line_start=40)
    expand = _node("expand", "kb_agent/query/expander.py", line_start=50)
    nodes = [dashboard, api, planner, retrieve, expand]
    edges = [
        SymbolEdge(source=dashboard.id, target=api.id, kind=EdgeKind.CALLS),
        SymbolEdge(source=planner.id, target=retrieve.id, kind=EdgeKind.CALLS, confidence=0.9),
        SymbolEdge(source=retrieve.id, target=expand.id, kind=EdgeKind.CALLS, confidence=0.8),
        SymbolEdge(source=api.id, target=planner.id, kind=EdgeKind.IMPORTS, confidence=0.7),
    ]

    storage = GraphStorage(graph_dir)
    storage.save(nodes, edges)
    storage.save_hotpath({
        retrieve.id: HotPathScore(node_id=retrieve.id, incoming_calls=2, hotness=1.0),
        planner.id: HotPathScore(node_id=planner.id, incoming_calls=1, hotness=0.5),
        api.id: HotPathScore(node_id=api.id, incoming_calls=1, hotness=0.4),
    })
    return kb


def _complete_path(client: TestClient, path_id: str) -> None:
    for lesson_id in ("lesson-1", "lesson-2", "lesson-3"):
        resp = client.post(f"/api/learning/paths/{path_id}/lessons/{lesson_id}/complete")
        assert resp.status_code == 200


def test_recommendations_continue_in_progress_path(tmp_path: Path):
    kb = _make_recommendation_kb(tmp_path)
    client = TestClient(create_app(kb))

    client.post("/api/learning/paths/architecture-overview/lessons/lesson-1/complete")
    resp = client.get("/api/learning/recommendations")

    assert resp.status_code == 200
    first = resp.json()["recommendations"][0]
    assert first["type"] == "continue_path"
    assert first["target"] == {
        "path_id": "architecture-overview",
        "lesson_id": "lesson-2",
        "topic_id": None,
    }
    assert {"incomplete_path", "path_progress"} <= set(first["signals"])


def test_recommendations_are_useful_for_fresh_learner(tmp_path: Path):
    kb = _make_recommendation_kb(tmp_path)
    client = TestClient(create_app(kb))

    data = client.get("/api/learning/recommendations").json()

    assert data["recommendations"]
    assert data["recommendations"][0]["type"] == "start_path"
    assert data["recommendations"][0]["target"]["path_id"] == "architecture-overview"


def test_recommendations_prioritize_prerequisite_topic_after_view(tmp_path: Path):
    kb = _make_recommendation_kb(tmp_path)
    client = TestClient(create_app(kb))
    retrieve_id = "repo/kb_agent/query/retrieval.py::retrieve"
    planner_id = "repo/kb_agent/query/planner.py::QueryPlanner"

    event_resp = client.post(
        "/api/learning/progress/events",
        json={"event_type": "topic_viewed", "context": {"page": "topic", "topic_id": retrieve_id}},
    )
    assert event_resp.status_code == 200

    data = client.get("/api/learning/recommendations").json()
    first = data["recommendations"][0]
    assert first["type"] == "open_topic"
    assert first["target"]["topic_id"] == planner_id
    assert "prerequisite" in first["signals"]
    assert first["target"]["topic_id"] != retrieve_id


def test_recommendations_advance_after_prerequisite_path_is_completed(tmp_path: Path):
    kb = _make_recommendation_kb(tmp_path)
    client = TestClient(create_app(kb))

    initial = client.get("/api/learning/recommendations").json()["recommendations"][0]
    assert initial["target"]["path_id"] == "architecture-overview"
    assert "prerequisite" in initial["signals"]

    _complete_path(client, "architecture-overview")
    next_rec = client.get("/api/learning/recommendations").json()["recommendations"][0]

    assert next_rec["type"] == "start_path"
    assert next_rec["target"]["path_id"] == "query-and-retrieval"
    assert "prerequisite" not in next_rec["signals"]


def test_recommendations_change_with_active_goal(tmp_path: Path):
    kb = _make_recommendation_kb(tmp_path)
    client = TestClient(create_app(kb))
    _complete_path(client, "architecture-overview")

    before = client.get("/api/learning/recommendations").json()["recommendations"]
    goal_resp = client.post(
        "/api/learning/progress/events",
        json={
            "event_type": "goal_updated",
            "context": {"page": "dashboard"},
            "metadata": {"goal": "retrieval"},
        },
    )
    assert goal_resp.status_code == 200

    after = client.get("/api/learning/recommendations").json()["recommendations"]
    assert after != before
    assert "active_goal" in set(after[0]["signals"])


def test_dashboard_uses_personalized_recommendation_topics_and_action(tmp_path: Path):
    kb = _make_recommendation_kb(tmp_path)
    client = TestClient(create_app(kb))
    retrieve_id = "repo/kb_agent/query/retrieval.py::retrieve"

    client.post(
        "/api/learning/progress/events",
        json={"event_type": "topic_viewed", "context": {"page": "topic", "topic_id": retrieve_id}},
    )
    data = client.get("/api/learning/dashboard").json()

    assert data["suggested_next_action"]["type"] == "open_topic"
    assert data["recommended_topics"][0]["title"] == "QueryPlanner"
    assert "prerequisite" in data["recommended_topics"][0]["matched_fields"]


def test_recommendations_fall_back_to_topics_when_all_paths_completed(tmp_path: Path):
    kb = _make_recommendation_kb(tmp_path)
    client = TestClient(create_app(kb))

    for path_id in (
        "architecture-overview",
        "query-and-retrieval",
        "knowledge-graph-construction",
    ):
        _complete_path(client, path_id)

    data = client.get("/api/learning/recommendations").json()

    assert data["recommendations"]
    assert data["recommendations"][0]["type"] == "open_topic"
    assert data["recommendations"][0]["target"]["path_id"] is None


def test_score_does_not_mutate_signal_list():
    signals = ["graph_centrality"]
    engine = LearningRecommendationEngine(
        paths=[
            LearningPathSummary(
                id="query-and-retrieval",
                title="Query and retrieval pipeline",
                description="Learn retrieval.",
            )
        ],
        nodes=[],
        edges=[],
        hotpath={},
        progress=UserProgress(active_learning_goal="retrieval"),
    )

    score = engine._score(0.5, "Query and retrieval pipeline")

    assert score == 0.62
    assert signals == ["graph_centrality"]
    assert engine._score_signals("Query and retrieval pipeline", signals=signals) == [
        "graph_centrality",
        "active_goal",
    ]
