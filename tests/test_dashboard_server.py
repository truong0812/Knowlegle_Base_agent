"""Tests for dashboard server — path traversal protection."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_agent.dashboard.server import create_app


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
