from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.graph.storage import GraphStorage


def _make_node(id: str = "repo/test.py::func()", name: str = "func") -> SymbolNode:
    return SymbolNode(
        id=id,
        name=name,
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        path="test.py",
        line_start=1,
        line_end=10,
    )


def _make_edge(source: str = "repo/a.py::f()", target: str = "repo/b.py::g()") -> SymbolEdge:
    return SymbolEdge(
        source=source,
        target=target,
        kind=EdgeKind.CALLS,
        confidence=0.75,
        source_type="heuristic",
        resolution="direct_import",
    )


class TestGraphStorage:
    def test_save_and_load_roundtrip(self, tmp_path: Path):
        storage = GraphStorage(tmp_path / "graph")
        nodes = [_make_node("repo/a.py::f()", "f"), _make_node("repo/b.py::g()", "g")]
        edges = [_make_edge()]

        storage.save(nodes, edges)
        loaded_nodes, loaded_edges = storage.load()

        assert len(loaded_nodes) == 2
        assert loaded_nodes[0].id == "repo/a.py::f()"
        assert loaded_nodes[1].id == "repo/b.py::g()"
        assert len(loaded_edges) == 1
        assert loaded_edges[0].source == "repo/a.py::f()"
        assert loaded_edges[0].kind == EdgeKind.CALLS
        assert loaded_edges[0].confidence == 0.75

    def test_adjacency_index_structure(self, tmp_path: Path):
        storage = GraphStorage(tmp_path / "graph")
        nodes = [_make_node("repo/a.py::f()", "f"), _make_node("repo/b.py::g()", "g")]
        edges = [_make_edge()]

        storage.save(nodes, edges)

        adj_path = tmp_path / "graph" / "adjacency.json"
        assert adj_path.exists()
        adj = json.loads(adj_path.read_text(encoding="utf-8"))

        assert "repo/a.py::f()" in adj
        assert adj["repo/a.py::f()"]["outgoing"] == ["0"]
        assert "repo/b.py::g()" in adj
        assert adj["repo/b.py::g()"]["incoming"] == ["0"]

    def test_load_missing_files(self, tmp_path: Path):
        storage = GraphStorage(tmp_path / "nonexistent")
        nodes, edges = storage.load()
        assert nodes == []
        assert edges == []
