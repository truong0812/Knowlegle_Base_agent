"""Tests for dashboard chat endpoint — intent routing, deterministic mode, citations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_agent.dashboard.server import create_app
from kb_agent.graph.features import Feature
from kb_agent.graph.hotpath import HotPathScore
from kb_agent.graph.storage import GraphStorage
from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_dashboard_server.py)
# ---------------------------------------------------------------------------

def _node(
    node_id: str,
    name: str,
    path: str = "src/auth.py",
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


def _build_kb(repo: Path) -> Path:
    """Create a minimal KB with two nodes and one edge for chat tests."""
    kb = repo / ".kb"
    graph_dir = kb / "graph"
    entries_dir = kb / "entries"
    entries_dir.mkdir(parents=True)

    manifest = {
        "version": "1.0",
        "source_repo": str(repo),
        "languages": ["python"],
        "stats": {"total_entries": 3},
        "created_at": "2026-05-29T10:00:00",
    }
    (kb / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (entries_dir / "arch_root.json").write_text(
        json.dumps({"ai": {"summary": "Sample learning project."}}),
        encoding="utf-8",
    )

    nodes = [
        _node("repo/src/auth.py::login", "login", line_start=3, line_end=8),
        _node("repo/src/auth.py::validate_token", "validate_token", line_start=10, line_end=20),
    ]
    edges = [
        SymbolEdge(
            source=nodes[0].id,
            target=nodes[1].id,
            kind=EdgeKind.CALLS,
            confidence=0.9,
        ),
    ]
    storage = GraphStorage(graph_dir)
    storage.save(nodes, edges)
    storage.save_features([
        Feature(
            id="feature.auth",
            name="auth",
            member_node_ids=[node.id for node in nodes],
            naming_basis="auth",
            edge_density=1,
        ),
    ])
    storage.save_hotpath({
        nodes[1].id: HotPathScore(
            node_id=nodes[1].id,
            incoming_calls=1,
            hotness=0.75,
        ),
    })
    return kb


@pytest.fixture
def _chat_client(tmp_path: Path, monkeypatch):
    """Create a test client with KB data, ensuring no LLM key."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    kb = _build_kb(tmp_path / "repo")
    app = create_app(kb)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Chat request helper
# ---------------------------------------------------------------------------

def _chat(client, question: str, node_id: str | None = None, active_view: str | None = None):
    payload = {"question": question, "context": {}, "history": []}
    if node_id:
        payload["context"]["node_id"] = node_id
    if active_view:
        payload["context"]["active_view"] = active_view
    return client.post("/api/chat", json=payload)


# ===========================================================================
# Test Classes
# ===========================================================================


class TestIntentRouting:
    """Intent router selects the correct KB tool based on question pattern."""

    def test_callers_pattern_routes_to_callers(self, _chat_client):
        resp = _chat(_chat_client, "Ai gọi login?", node_id="repo/src/auth.py::login")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        # Answer should mention callers
        assert "login" in data["answer"].lower() or "caller" in data["answer"].lower()

    def test_callers_english_pattern(self, _chat_client):
        resp = _chat(_chat_client, "Who calls login?", node_id="repo/src/auth.py::login")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None

    def test_callees_pattern(self, _chat_client):
        resp = _chat(_chat_client, "login gọi gì?", node_id="repo/src/auth.py::login")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert "validate_token" in data["answer"]

    def test_callees_english_pattern(self, _chat_client):
        resp = _chat(_chat_client, "What does login call?", node_id="repo/src/auth.py::login")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None

    def test_impact_pattern(self, _chat_client):
        resp = _chat(_chat_client, "Ảnh hưởng nếu sửa validate_token?", node_id="repo/src/auth.py::validate_token")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert "validate_token" in data["answer"] or "impact" in data["answer"].lower()

    def test_explain_pattern_with_node(self, _chat_client):
        resp = _chat(_chat_client, "login làm gì?", node_id="repo/src/auth.py::login")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert "login" in data["answer"]

    def test_general_without_node(self, _chat_client):
        resp = _chat(_chat_client, "Repo này làm gì?")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        # General intent should still produce an answer
        assert len(data["answer"]) > 0

    def test_no_node_id_falls_back_to_general(self, _chat_client):
        resp = _chat(_chat_client, "Ai gọi login?")
        assert resp.status_code == 200
        data = resp.json()
        # Without node_id, intent falls to general
        assert data["error"] is None


class TestDeterministicMode:
    """Chat works without OPENAI_API_KEY."""

    def test_chat_returns_answer(self, _chat_client):
        resp = _chat(_chat_client, "login làm gì?", node_id="repo/src/auth.py::login")
        data = resp.json()
        assert data["error"] is None
        assert len(data["answer"]) > 0

    def test_chat_returns_citations(self, _chat_client):
        resp = _chat(_chat_client, "Ai gọi validate_token?", node_id="repo/src/auth.py::validate_token")
        data = resp.json()
        assert len(data["citations"]) > 0
        cit = data["citations"][0]
        assert "label" in cit
        assert "path" in cit
        assert "node_id" in cit

    def test_chat_returns_suggested_questions(self, _chat_client):
        resp = _chat(_chat_client, "login làm gì?", node_id="repo/src/auth.py::login")
        data = resp.json()
        assert isinstance(data["suggested_questions"], list)
        assert len(data["suggested_questions"]) > 0


class TestContextResolution:
    """Context fields are used correctly."""

    def test_resolves_node_id_from_context(self, _chat_client):
        # Use node name instead of full ID
        resp = _chat(_chat_client, "làm gì?", node_id="login")
        data = resp.json()
        assert data["error"] is None
        assert "login" in data["answer"]

    def test_generates_overview_suggestions(self, _chat_client):
        resp = _chat(_chat_client, "Repo này làm gì?", active_view="overview")
        data = resp.json()
        suggestions = data["suggested_questions"]
        assert any("module" in s.lower() or "repo" in s.lower() or "flow" in s.lower() for s in suggestions)

    def test_generates_node_suggestions(self, _chat_client):
        resp = _chat(_chat_client, "làm gì?", node_id="repo/src/auth.py::login", active_view="node")
        data = resp.json()
        suggestions = data["suggested_questions"]
        # Node-specific suggestions should mention the symbol name
        assert any("login" in s for s in suggestions)

    def test_generates_features_suggestions(self, _chat_client):
        resp = _chat(_chat_client, "Feature này làm gì?", active_view="features")
        data = resp.json()
        suggestions = data["suggested_questions"]
        assert any("feature" in s.lower() or "symbol" in s.lower() for s in suggestions)


class TestErrorHandling:
    """Error responses are structured correctly."""

    def test_missing_kb_returns_error(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        kb = tmp_path / "repo" / ".kb"
        kb.mkdir(parents=True)
        client = TestClient(create_app(kb))

        resp = client.post("/api/chat", json={
            "question": "test",
            "context": {},
            "history": [],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is not None
        assert data["error"]["code"] == "missing_kb"

    def test_response_structure_on_error(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        kb = tmp_path / "repo" / ".kb"
        kb.mkdir(parents=True)
        client = TestClient(create_app(kb))

        resp = client.post("/api/chat", json={
            "question": "test",
            "context": {},
            "history": [],
        })

        data = resp.json()
        assert "answer" in data
        assert "citations" in data
        assert "suggested_questions" in data
        assert "error" in data


class TestCitationGeneration:
    """Citations are correctly extracted from tool results."""

    def test_callers_response_has_citations(self, _chat_client):
        resp = _chat(_chat_client, "Ai gọi validate_token?", node_id="repo/src/auth.py::validate_token")
        data = resp.json()
        assert len(data["citations"]) > 0
        # Should cite validate_token
        cited_ids = [c["node_id"] for c in data["citations"] if c.get("node_id")]
        assert "repo/src/auth.py::validate_token" in cited_ids

    def test_citation_fields_complete(self, _chat_client):
        resp = _chat(_chat_client, "login làm gì?", node_id="repo/src/auth.py::login")
        data = resp.json()
        if data["citations"]:
            cit = data["citations"][0]
            assert "label" in cit
            assert cit["label"]  # non-empty
            assert "path" in cit
            assert "line_start" in cit
            assert "line_end" in cit
            assert "node_id" in cit
