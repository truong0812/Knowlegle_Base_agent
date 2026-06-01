from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.graph.storage import GraphStorage, ReadOnlyStorage


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

    def test_save_and_load_empty(self, tmp_path: Path):
        storage = GraphStorage(tmp_path / "graph")
        storage.save([], [])

        nodes, edges = storage.load()
        assert nodes == []
        assert edges == []

    def test_load_hotpath_missing_file(self, tmp_path: Path):
        storage = GraphStorage(tmp_path / "nonexistent")
        assert storage.load_hotpath() == {}

    def test_save_and_load_hotpath_roundtrip(self, tmp_path: Path):
        from kb_agent.graph.hotpath import HotPathScore
        storage = GraphStorage(tmp_path / "graph")
        scores = {
            "node_a": HotPathScore(node_id="node_a", incoming_calls=5, hotness=0.9),
            "node_b": HotPathScore(node_id="node_b", incoming_calls=0, hotness=0.0),
        }
        storage.save_hotpath(scores)
        loaded = storage.load_hotpath()
        assert len(loaded) == 2
        assert loaded["node_a"].hotness == 0.9
        assert loaded["node_a"].incoming_calls == 5
        assert loaded["node_b"].hotness == 0.0

    def test_save_empty_hotpath(self, tmp_path: Path):
        storage = GraphStorage(tmp_path / "graph")
        storage.save_hotpath({})
        assert storage.load_hotpath() == {}

    def test_adjacency_with_no_edges(self, tmp_path: Path):
        storage = GraphStorage(tmp_path / "graph")
        nodes = [_make_node("repo/a.py::f()", "f")]
        storage.save(nodes, [])

        adj = json.loads((tmp_path / "graph" / "adjacency.json").read_text(encoding="utf-8"))
        assert "repo/a.py::f()" in adj
        assert adj["repo/a.py::f()"]["outgoing"] == []
        assert adj["repo/a.py::f()"]["incoming"] == []


class TestReadOnlyStorageABC:
    def test_graph_storage_is_readonly_storage(self):
        assert issubclass(GraphStorage, ReadOnlyStorage)

    def test_cannot_instantiate_abc_directly(self):
        with pytest.raises(TypeError):
            ReadOnlyStorage()  # type: ignore[abstract]

    def test_readonly_interface_has_required_methods(self):
        required = {"load", "load_hotpath", "load_features"}
        actual = {m for m in dir(ReadOnlyStorage) if not m.startswith("_")}
        assert required.issubset(actual)

    def test_readonly_typed_storage_works(self, tmp_path: Path):
        storage: ReadOnlyStorage = GraphStorage(tmp_path / "graph")
        assert isinstance(storage, ReadOnlyStorage)
        nodes, edges = storage.load()
        assert nodes == []
        assert storage.load_hotpath() == {}
        assert storage.load_features() == []
