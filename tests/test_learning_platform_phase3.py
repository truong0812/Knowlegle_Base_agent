"""Phase 3 tests for learner-friendly topic pages."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from kb_agent.dashboard.server import create_app
from kb_agent.graph.storage import GraphStorage
from kb_agent.learning.api import LearningApi
from kb_agent.learning.models import TopicPage
from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode


def _node(
    node_id: str,
    name: str,
    path: str,
    *,
    kind: SymbolKind = SymbolKind.FUNCTION,
    line_start: int = 1,
    line_end: int = 10,
    signature: str | None = None,
    docstring: str | None = None,
) -> SymbolNode:
    return SymbolNode(
        id=node_id,
        name=name,
        kind=kind,
        language=Language.PYTHON,
        path=path,
        line_start=line_start,
        line_end=line_end,
        signature=signature or f"def {name}():",
        docstring=docstring,
    )


def _make_topic_kb(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    kb = repo / ".kb"
    graph_dir = kb / "graph"
    kb.mkdir(parents=True)
    (kb / "manifest.json").write_text(
        json.dumps({
            "source_repo": str(repo),
            "stats": {"total_entries": 2},
            "created_at": "2026-06-02T10:00:00",
        }),
        encoding="utf-8",
    )

    retrieve = _node(
        "repo/src/retrieval.py::retrieve",
        "retrieve",
        "src/retrieval.py",
        line_start=3,
        line_end=24,
        signature="def retrieve(query: str) -> list[str]:",
        docstring="Find source-backed context for a learner question.",
    )
    expand = _node(
        "repo/src/retrieval.py::expand",
        "expand",
        "src/retrieval.py",
        line_start=26,
        line_end=44,
    )
    planner = _node(
        "repo/src/planner.py::QueryPlanner",
        "QueryPlanner",
        "src/planner.py",
        kind=SymbolKind.CLASS,
        line_start=5,
        line_end=30,
    )
    edges = [
        SymbolEdge(source=retrieve.id, target=expand.id, kind=EdgeKind.CALLS, confidence=0.9),
        SymbolEdge(source=planner.id, target=retrieve.id, kind=EdgeKind.USES_TYPE, confidence=0.8),
    ]
    GraphStorage(graph_dir).save([retrieve, expand, planner], edges)
    return kb


def test_topic_page_includes_explanation_relationships_and_cache(tmp_path: Path):
    kb = _make_topic_kb(tmp_path)
    client = TestClient(create_app(kb))

    resp = client.get("/api/learning/topics/retrieve")

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "retrieve"
    assert "source-backed" in data["explanation"]
    assert data["why_it_matters"]
    assert data["citations"][0]["path"] == "src/retrieval.py"
    assert data["examples"][0] == "def retrieve(query: str) -> list[str]:"
    assert data["related_topics"] == [
        "repo/src/retrieval.py::expand",
        "repo/src/planner.py::QueryPlanner",
    ]
    assert data["prerequisites"] == ["repo/src/planner.py::QueryPlanner"]
    assert data["graph_context"]["relationships"][0]["kind"] == "calls"
    assert data["progress"]["viewed"] is True

    cache_path = kb / "learning" / "topics.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert "repo/src/retrieval.py::retrieve" not in cache
    cached_pages = list(cache.values())
    assert cached_pages[0]["id"] == "repo/src/retrieval.py::retrieve"
    assert cached_pages[0]["metadata"]["prompt_version"] == "topic_explainer.v1"


def test_topic_search_matches_path_kind_and_signature(tmp_path: Path):
    kb = _make_topic_kb(tmp_path)
    client = TestClient(create_app(kb))

    by_path = client.get("/api/learning/topics/search?q=planner").json()
    assert by_path["results"][0]["title"] == "QueryPlanner"
    assert "summary" in by_path["results"][0]["matched_fields"]

    by_signature = client.get("/api/learning/topics/search?q=query").json()
    titles = [item["title"] for item in by_signature["results"]]
    assert "retrieve" in titles
    assert "QueryPlanner" in titles


def test_topic_page_missing_graph_degrades_with_warning(tmp_path: Path):
    kb = tmp_path / "repo" / ".kb"
    kb.mkdir(parents=True)
    client = TestClient(create_app(kb))

    resp = client.get("/api/learning/topics/missing-topic")

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "unknown"
    assert {warning["code"] for warning in data["warnings"]} >= {
        "missing_kb",
        "topic_not_found",
    }


def test_topic_cache_invalid_json_is_ignored(tmp_path: Path):
    kb = _make_topic_kb(tmp_path)
    learning_dir = kb / "learning"
    learning_dir.mkdir()
    (learning_dir / "topics.json").write_text("{not-json", encoding="utf-8")
    client = TestClient(create_app(kb))

    resp = client.get("/api/learning/topics/retrieve")

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "retrieve"
    cache = json.loads((learning_dir / "topics.json").read_text(encoding="utf-8"))
    assert list(cache.values())[0]["id"] == "repo/src/retrieval.py::retrieve"


def test_topic_explainer_error_returns_structured_warning(tmp_path: Path):
    kb = _make_topic_kb(tmp_path)
    nodes, _ = GraphStorage(kb / "graph").load()

    class FailingExplainer:
        def resolve(self, topic_id: str):
            return nodes[0]

        def explain(self, *args, **kwargs) -> TopicPage:
            raise RuntimeError("boom")

    api = LearningApi(kb)
    api._topic_explainer_cache = FailingExplainer()  # type: ignore[assignment]

    page = api.topic("retrieve")

    assert page.type == "unknown"
    assert page.progress.viewed is True
    assert page.warnings[-1].code == "topic_explainer_error"
