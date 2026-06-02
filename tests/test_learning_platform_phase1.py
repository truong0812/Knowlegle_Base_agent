"""Phase 1 tests for AI learning platform contracts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_agent.dashboard.server import create_app
from kb_agent.graph.features import Feature
from kb_agent.graph.hotpath import HotPathScore
from kb_agent.graph.storage import GraphStorage
from kb_agent.learning.api import LearningApi
from kb_agent.learning.models import KbStatus, ProjectSummary, TutorRequest
from kb_agent.learning.tutor import LearningTutor
from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode


class FakeStorage:
    def __init__(self, nodes: list[SymbolNode], edges: list[SymbolEdge] | None = None):
        self.nodes = nodes
        self.edges = edges or []
        self.load_count = 0

    def load(self) -> tuple[list[SymbolNode], list[SymbolEdge]]:
        self.load_count += 1
        return self.nodes, self.edges

    def load_hotpath(self) -> dict[str, HotPathScore]:
        return {}

    def load_features(self) -> list[Feature]:
        return []


class FakeStreamingTutorClient:
    model_name = "fake-stream"

    def __init__(self) -> None:
        self.complete_called = False
        self.stream_called = False
        self.prompt = ""

    def complete(self, prompt: str, context):
        self.complete_called = True
        raise AssertionError("streaming path should not call complete")

    def stream(self, prompt: str, context):
        self.stream_called = True
        self.prompt = prompt
        yield "streamed "
        yield "answer"


def _node(
    node_id: str,
    name: str,
    path: str = "src/retrieval.py",
    line_start: int = 1,
    line_end: int = 10,
) -> SymbolNode:
    return SymbolNode(
        id=node_id,
        name=name,
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        path=path,
        line_start=line_start,
        line_end=line_end,
        signature=f"def {name}():",
    )


@pytest.fixture
def learning_kb(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    kb = repo / ".kb"
    graph_dir = kb / "graph"
    entries_dir = kb / "entries"
    entries_dir.mkdir(parents=True)

    (kb / "manifest.json").write_text(
        json.dumps({
            "version": "1.0",
            "source_repo": str(repo),
            "languages": ["python"],
            "stats": {"total_entries": 3},
            "created_at": "2026-06-02T10:00:00",
        }),
        encoding="utf-8",
    )
    (entries_dir / "arch_root.json").write_text(
        json.dumps({"ai": {"summary": "Sample learning platform project."}}),
        encoding="utf-8",
    )

    nodes = [
        _node("repo/src/retrieval.py::retrieve", "retrieve", line_start=3, line_end=20),
        _node("repo/src/retrieval.py::expand", "expand", line_start=22, line_end=40),
    ]
    edges = [
        SymbolEdge(
            source=nodes[0].id,
            target=nodes[1].id,
            kind=EdgeKind.CALLS,
            confidence=0.9,
        )
    ]
    storage = GraphStorage(graph_dir)
    storage.save(nodes, edges)
    storage.save_features([
        Feature(
            id="feature.retrieval",
            name="retrieval",
            member_node_ids=[node.id for node in nodes],
            naming_basis="retrieval",
            edge_density=1.0,
        )
    ])
    return kb


@pytest.fixture
def learning_client(learning_kb: Path) -> TestClient:
    return TestClient(create_app(learning_kb))


class TestLearningDashboardContract:
    def test_dashboard_returns_learning_contract(self, learning_client: TestClient):
        resp = learning_client.get("/api/learning/dashboard")

        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["description"] == "Sample learning platform project."
        assert data["kb_status"]["available"] is True
        assert data["kb_status"]["node_count"] == 2
        assert data["kb_status"]["edge_count"] == 1
        assert data["progress"] == {
            "completed_lessons": 0,
            "viewed_topics": 0,
            "active_path_id": None,
            "last_context": None,
        }
        assert data["recommended_paths"][0]["id"] == "architecture-overview"
        assert data["important_features"][0]["id"] == "feature.retrieval"
        assert data["suggested_next_action"]["type"] == "start_path"

    def test_dashboard_missing_kb_returns_warning(self, tmp_path: Path):
        kb = tmp_path / "repo" / ".kb"
        kb.mkdir(parents=True)
        client = TestClient(create_app(kb))

        resp = client.get("/api/learning/dashboard")

        assert resp.status_code == 200
        data = resp.json()
        assert data["kb_status"]["available"] is False
        assert data["kb_status"]["warnings"][0]["code"] == "missing_kb"
        assert data["suggested_next_action"]["type"] == "open_graph"

    def test_learning_api_accepts_injected_storage(self, tmp_path: Path):
        node = _node("repo/src/retrieval.py::retrieve", "retrieve")
        storage = FakeStorage([node])
        kb = tmp_path / "repo" / ".kb"
        kb.mkdir(parents=True)
        (kb / "manifest.json").write_text(
            json.dumps({"source_repo": str(tmp_path / "repo"), "stats": {"total_entries": 1}}),
            encoding="utf-8",
        )

        api = LearningApi(kb, storage=storage)
        status = api.kb_status()

        assert status.node_count == 1
        assert storage.load_count == 1

    def test_learning_api_accepts_injected_tutor_factory(self, tmp_path: Path):
        node = _node("repo/src/retrieval.py::retrieve", "retrieve")
        storage = FakeStorage([node])
        captured_kwargs = []
        kb = tmp_path / "repo" / ".kb"
        kb.mkdir(parents=True)
        (kb / "manifest.json").write_text(
            json.dumps({"source_repo": str(tmp_path / "repo"), "stats": {"total_entries": 1}}),
            encoding="utf-8",
        )

        def tutor_factory(**kwargs):
            captured_kwargs.append(kwargs)
            return LearningTutor(**kwargs)

        api = LearningApi(kb, storage=storage, tutor_factory=tutor_factory)
        response = api.tutor(TutorRequest(message="Explain retrieve"))

        assert response.graph_context["nodes"][0]["name"] == "retrieve"
        assert captured_kwargs[0]["nodes"] == [node]
        assert isinstance(captured_kwargs[0]["status"], KbStatus)


class TestLearningPathContracts:
    def test_paths_list_returns_starter_paths(self, learning_client: TestClient):
        resp = learning_client.get("/api/learning/paths")

        assert resp.status_code == 200
        data = resp.json()
        assert [path["id"] for path in data["paths"]] == [
            "architecture-overview",
            "query-and-retrieval",
            "knowledge-graph-construction",
        ]
        assert data["paths"][0]["status"] == "not_started"

    def test_path_detail_returns_lessons_and_progress(self, learning_client: TestClient):
        resp = learning_client.get("/api/learning/paths/architecture-overview")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "architecture-overview"
        assert len(data["lessons"]) == 3
        assert data["lessons"][0]["next_lesson_id"] == "lesson-2"
        assert data["progress"]["status"] == "not_started"

    def test_unknown_path_returns_404(self, learning_client: TestClient):
        resp = learning_client.get("/api/learning/paths/missing")

        assert resp.status_code == 404

    def test_complete_lesson_returns_next_action(self, learning_client: TestClient):
        resp = learning_client.post(
            "/api/learning/paths/architecture-overview/lessons/lesson-1/complete"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is True
        assert data["progress"]["completed_lesson_count"] == 1
        assert data["progress"]["status"] == "in_progress"
        assert data["next_action"]["target_id"] == "lesson-2"

        detail_resp = learning_client.get("/api/learning/paths/architecture-overview")
        detail = detail_resp.json()
        assert detail["lessons"][0]["completed"] is True
        assert detail["progress"]["completed_lesson_count"] == 1

        progress_resp = learning_client.get("/api/learning/progress")
        progress = progress_resp.json()
        assert progress["completed_lessons"][0]["path_id"] == "architecture-overview"
        assert progress["completed_lessons"][0]["lesson_id"] == "lesson-1"


class TestTopicContracts:
    def test_topic_page_returns_citation_and_graph_context(self, learning_client: TestClient):
        resp = learning_client.get("/api/learning/topics/retrieve")

        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "retrieve"
        assert data["citations"][0]["path"] == "src/retrieval.py"
        assert data["graph_context"]["nodes"][0]["name"] == "retrieve"
        assert data["progress"]["viewed"] is True

    def test_missing_topic_returns_structured_warning(self, learning_client: TestClient):
        resp = learning_client.get("/api/learning/topics/does-not-exist")

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "unknown"
        assert data["warnings"][0]["code"] == "topic_not_found"

    def test_topic_search_returns_matches(self, learning_client: TestClient):
        resp = learning_client.get("/api/learning/topics/search?q=retr")

        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "retr"
        assert data["results"][0]["title"] == "retrieve"

    def test_topic_search_empty_query_returns_empty_results(self, learning_client: TestClient):
        resp = learning_client.get("/api/learning/topics/search?q=")

        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == ""
        assert data["results"] == []


class TestTutorProgressAndRecommendations:
    def test_tutor_chat_returns_natural_language_contract(self, learning_client: TestClient):
        resp = learning_client.post(
            "/api/learning/tutor/chat",
            json={
                "message": "What should I learn first about retrieve?",
                "stream": False,
                "context": {"page": "dashboard"},
                "learner": {"level": "beginner"},
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["answer"], str)
        assert len(data["answer"]) > 40
        assert data["citations"][0]["path"] == "src/retrieval.py"
        assert data["recommended_next_steps"][0]["type"] == "open_topic"
        assert data["graph_context"]["nodes"][0]["name"] == "retrieve"
        assert data["warnings"][0]["code"] == "llm_unavailable"

    def test_tutor_chat_uses_topic_context_and_relationships(self, learning_client: TestClient):
        resp = learning_client.post(
            "/api/learning/tutor/chat",
            json={
                "message": "Explain this simply",
                "context": {"page": "topic", "topic_id": "retrieve"},
                "learner": {"level": "beginner"},
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "Answered with context from retrieve."
        assert data["related_topics"] == []
        assert data["graph_context"]["relationships"][0]["kind"] == "calls"
        assert data["suggested_questions"][0] == "Can you explain retrieve more simply?"

    def test_tutor_chat_stream_returns_sse_events(self, learning_client: TestClient):
        with learning_client.stream(
            "POST",
            "/api/learning/tutor/chat?stream=true",
            json={
                "message": "Explain retrieve",
                "context": {"page": "topic", "topic_id": "retrieve"},
            },
        ) as resp:
            body = "".join(resp.iter_text())

        assert resp.status_code == 200
        assert "event: status" in body
        assert "event: token" in body
        assert "event: citation" in body
        assert "event: done" in body

    def test_tutor_chat_stream_request_flag_returns_sse_events(self, learning_client: TestClient):
        with learning_client.stream(
            "POST",
            "/api/learning/tutor/chat",
            json={
                "message": "Explain retrieve",
                "stream": True,
                "context": {"page": "topic", "topic_id": "retrieve"},
            },
        ) as resp:
            body = "".join(resp.iter_text())

        assert resp.status_code == 200
        assert "event: token" in body
        assert "event: done" in body

    def test_tutor_stream_uses_llm_stream_client(self):
        node = _node("repo/src/retrieval.py::retrieve", "retrieve")
        client = FakeStreamingTutorClient()
        tutor = LearningTutor(
            nodes=[node],
            edges=[],
            status=KbStatus(available=True, node_count=1),
            project_summary=ProjectSummary(project_name="repo"),
            llm_client=client,
        )

        events = list(tutor.stream_events(
            request=TutorRequest(
                message="Explain retrieve",
                context={"page": "topic", "topic_id": "retrieve"},
            )
        ))

        assert client.stream_called is True
        assert client.complete_called is False
        assert "Prompt version: tutor_answer.v1" in client.prompt
        assert '"nodes":' in client.prompt
        assert [event["event"] for event in events].count("token") == 2
        assert events[-1]["data"]["answer"] == "streamed answer"

    def test_tutor_empty_graph_fallback_is_structured(self, tmp_path: Path):
        kb = tmp_path / "repo" / ".kb"
        kb.mkdir(parents=True)
        client = TestClient(create_app(kb))

        resp = client.post(
            "/api/learning/tutor/chat",
            json={"message": "", "context": {"page": "dashboard"}},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["citations"] == []
        assert data["graph_context"] == {"nodes": [], "relationships": []}
        assert data["recommended_next_steps"][0]["type"] == "start_path"
        assert {warning["code"] for warning in data["warnings"]} >= {
            "missing_kb",
            "missing_graph_context",
            "llm_unavailable",
        }

    def test_progress_contract_and_event_acceptance(self, learning_client: TestClient):
        progress_resp = learning_client.get("/api/learning/progress")
        assert progress_resp.status_code == 200
        assert progress_resp.json()["preferred_explanation_level"] == "beginner"

        event_resp = learning_client.post(
            "/api/learning/progress/events",
            json={
                "event_type": "topic_viewed",
                "context": {"page": "topic", "topic_id": "retrieve"},
                "metadata": {"source": "test"},
            },
        )
        assert event_resp.status_code == 200
        assert event_resp.json()["accepted"] is True
        assert event_resp.json()["progress"]["viewed_topics"][0]["topic_id"] == "retrieve"

        progress_resp = learning_client.get("/api/learning/progress")
        assert progress_resp.json()["viewed_topics"][0]["topic_id"] == "retrieve"

    def test_recommendations_contract(self, learning_client: TestClient):
        resp = learning_client.get("/api/learning/recommendations")

        assert resp.status_code == 200
        data = resp.json()
        assert data["recommendations"][0]["type"] == "start_path"
        assert "signals" in data["recommendations"][0]
