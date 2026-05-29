"""Tests for dashboard server — path traversal protection."""
from __future__ import annotations

import os
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


@pytest.fixture
def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    kb = repo / ".kb"
    kb.mkdir(parents=True)
    (kb / "graph").mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    return repo


@pytest.fixture
def client(_repo: Path):
    app = create_app(_repo / ".kb")
    return TestClient(app)


class TestPathTraversal:
    def test_legitimate_file(self, client, _repo: Path):
        resp = client.get("/api/file/src/main.py")
        assert resp.status_code == 200
        assert resp.json()["lines"] == ["print('hello')"]

    def test_traversal_outside_repo(self, client, _repo: Path):
        # Build a traversal path that escapes repo on any OS
        target = (_repo.parent.parent / "secret.txt").resolve()
        traversal = os.path.relpath(str(target), str(_repo))
        resp = client.get(f"/api/file/{traversal}")
        assert resp.status_code == 403

    def test_absolute_path_outside_repo(self, client):
        resp = client.get("/api/file//etc/passwd")
        assert resp.status_code == 403

    def test_nonexistent_file(self, client):
        resp = client.get("/api/file/src/missing.py")
        assert resp.status_code == 404

    def test_directory_rejected(self, client):
        resp = client.get("/api/file/src")
        assert resp.status_code == 404


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


class TestOverviewApi:
    def test_overview_returns_stats_features_and_hot_symbols(self, tmp_path: Path):
        kb = _build_kb(tmp_path / "repo")
        client = TestClient(create_app(kb))

        resp = client.get("/api/overview")

        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert data["summary"] == "Sample learning project."
        assert data["source_repo"] == str(tmp_path / "repo")
        assert data["stats"] == {"total_entries": 3, "node_count": 2, "edge_count": 1}
        assert data["languages"] == ["python"]
        assert data["top_features"][0]["id"] == "feature.auth"
        assert data["top_features"][0]["member_count"] == 2
        assert data["top_hot_symbols"][0]["name"] == "validate_token"
        assert data["top_modules"] == ["src.auth.py"]

    def test_overview_returns_structured_error_when_kb_missing(self, tmp_path: Path):
        kb = tmp_path / "repo" / ".kb"
        kb.mkdir(parents=True)
        client = TestClient(create_app(kb))

        resp = client.get("/api/overview")

        assert resp.status_code == 200
        data = resp.json()
        assert data["error"]["code"] == "missing_kb"
        assert data["stats"] is None
        assert data["top_features"] == []

    def test_overview_falls_back_for_hotpath_node_missing_from_graph(self, tmp_path: Path):
        kb = _build_kb(tmp_path / "repo")
        GraphStorage(kb / "graph").save_hotpath({
            "repo/src/auth.py::deleted": HotPathScore(
                node_id="repo/src/auth.py::deleted",
                incoming_calls=2,
                hotness=0.9,
            ),
        })
        client = TestClient(create_app(kb))

        resp = client.get("/api/overview")

        assert resp.status_code == 200
        hot_symbol = resp.json()["top_hot_symbols"][0]
        assert hot_symbol["node_id"] == "repo/src/auth.py::deleted"
        assert hot_symbol["name"] == "repo/src/auth.py::deleted"
        assert hot_symbol["path"] is None


class TestFeatureDetailApi:
    def test_feature_detail_returns_member_nodes_and_files(self, tmp_path: Path):
        kb = _build_kb(tmp_path / "repo")
        client = TestClient(create_app(kb))

        resp = client.get("/api/features/feature.auth")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "feature.auth"
        assert data["member_count"] == 2
        assert [member["name"] for member in data["members"]] == ["login", "validate_token"]
        assert "id" not in data["members"][0]
        assert data["members"][0]["node_id"] == "repo/src/auth.py::login"
        assert data["members"][1]["hotness"] == 0.75
        assert data["related_files"] == ["src/auth.py"]

    def test_feature_detail_unknown_feature_returns_404(self, tmp_path: Path):
        kb = _build_kb(tmp_path / "repo")
        client = TestClient(create_app(kb))

        resp = client.get("/api/features/feature.missing")

        assert resp.status_code == 404
