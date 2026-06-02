"""Phase 2 refactoring tests: decoupling, error handling, regression guards."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from kb_agent.dashboard.server import create_app
from kb_agent.learning.api import LearningApi
from kb_agent.learning.models import (
    KbStatus,
    ProjectSummary,
    TutorRequest,
    TutorResponse,
    WarningInfo,
)
from kb_agent.learning.tutor import default_tutor_factory
from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import SymbolNode


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


def _make_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "repo" / ".kb"
    kb.mkdir(parents=True)
    (kb / "manifest.json").write_text(
        json.dumps({"source_repo": str(tmp_path / "repo"), "stats": {"total_entries": 0}}),
        encoding="utf-8",
    )
    return kb


class StubTutor:
    """Minimal tutor satisfying the Tutor Protocol via structural subtyping."""

    def __init__(self, **kwargs) -> None:
        self.constructor_kwargs = kwargs

    def answer(self, request: TutorRequest) -> TutorResponse:
        return TutorResponse(
            answer="stub answer",
            summary="stub tutor",
            warnings=[WarningInfo(code="stub", message="stub tutor")],
        )

    def stream_events(self, request: TutorRequest):
        yield {"event": "status", "data": {"message": "stub"}}
        yield {"event": "done", "data": {"answer": "stub streamed"}}


class FailingTutor:
    """Tutor that raises on answer() to test server error handling."""

    def __init__(self, **kwargs) -> None:
        pass

    def answer(self, request: TutorRequest) -> TutorResponse:
        raise RuntimeError("tutor engine crash")

    def stream_events(self, request: TutorRequest):
        yield {"event": "status", "data": {"message": "starting"}}
        raise RuntimeError("tutor stream crash")


class TestTutorProtocolDecoupling:
    def test_stub_tutor_injected_via_factory(self, tmp_path: Path):
        """LearningApi works with any object satisfying the Tutor Protocol."""
        kb = _make_kb(tmp_path)
        api = LearningApi(kb, tutor_factory=StubTutor)

        response = api.tutor(TutorRequest(message="test"))
        assert response.answer == "stub answer"
        assert response.warnings[0].code == "stub"

    def test_stub_tutor_stream_via_factory(self, tmp_path: Path):
        """LearningApi stream_events delegates to the injected tutor."""
        kb = _make_kb(tmp_path)
        api = LearningApi(kb, tutor_factory=StubTutor)

        events = list(api.tutor_stream_events(TutorRequest(message="test")))
        assert events[0]["event"] == "status"
        assert events[-1]["event"] == "done"

    def test_default_tutor_factory_creates_working_tutor(self):
        node = _node("repo/src/retrieval.py::retrieve", "retrieve")
        tutor = default_tutor_factory(
            nodes=[node],
            edges=[],
            status=KbStatus(available=True, node_count=1),
            project_summary=ProjectSummary(project_name="test"),
        )

        response = tutor.answer(TutorRequest(message="Explain retrieve"))
        assert isinstance(response, TutorResponse)
        assert len(response.answer) > 0

    def test_api_module_does_not_import_learning_tutor_concrete(self):
        """Regression guard: api.py must not reference LearningTutor directly."""
        mod = importlib.import_module("kb_agent.learning.api")
        assert "LearningTutor" not in dir(mod), (
            "LearningApi should depend on the Tutor Protocol, not the concrete LearningTutor class."
        )


class TestServerErrorHandling:
    def test_non_streaming_tutor_returns_500_on_crash(self, tmp_path: Path):
        kb = _make_kb(tmp_path)
        client = TestClient(create_app(kb, tutor_factory=FailingTutor))

        resp = client.post(
            "/api/learning/tutor/chat",
            json={"message": "trigger crash"},
        )

        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"]["code"] == "tutor_error"

    def test_streaming_tutor_emits_error_event_on_crash(self, tmp_path: Path):
        kb = _make_kb(tmp_path)
        client = TestClient(create_app(kb, tutor_factory=FailingTutor))

        with client.stream(
            "POST",
            "/api/learning/tutor/chat?stream=true",
            json={"message": "trigger crash"},
        ) as resp:
            body = "".join(resp.iter_text())

        assert resp.status_code == 200
        assert "event: error" in body
        assert "tutor_stream_error" in body

    def test_non_streaming_tutor_returns_200_on_normal_operation(self, tmp_path: Path):
        """Verify the happy path still returns 200 after adding try-except."""
        kb = _make_kb(tmp_path)
        client = TestClient(create_app(kb))

        resp = client.post(
            "/api/learning/tutor/chat",
            json={"message": "Hello"},
        )

        assert resp.status_code == 200
        assert "answer" in resp.json()
