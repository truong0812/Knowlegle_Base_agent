"""Tests for hot-path scoring."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb_agent.graph.hotpath import HotPathScore, HotPathScorer
from kb_agent.graph.storage import GraphStorage
from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode


def _node(name: str, path: str = "svc.py", line: int = 1) -> SymbolNode:
    return SymbolNode(
        id=f"repo/{path}::{name}",
        name=name,
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        path=path,
        line_start=line,
        line_end=line + 5,
    )


def _edge(src: str, tgt: str, kind: EdgeKind = EdgeKind.CALLS, conf: float = 0.80) -> SymbolEdge:
    return SymbolEdge(source=src, target=tgt, kind=kind, confidence=conf)


class TestHotPathScorer:
    def test_single_node_no_calls(self):
        nodes = [_node("a")]
        edges: list[SymbolEdge] = []
        scorer = HotPathScorer(nodes, edges)
        scores = scorer.score_nodes()
        assert scores["repo/svc.py::a"].hotness == 0.0
        assert scores["repo/svc.py::a"].incoming_calls == 0

    def test_one_hot_node(self):
        nodes = [_node("a"), _node("b"), _node("c")]
        edges = [
            _edge("repo/svc.py::b", "repo/svc.py::a"),
            _edge("repo/svc.py::c", "repo/svc.py::a"),
            _edge("repo/svc.py::c", "repo/svc.py::b"),
        ]
        scorer = HotPathScorer(nodes, edges)
        scores = scorer.score_nodes()
        assert scores["repo/svc.py::a"].hotness == 1.0
        assert scores["repo/svc.py::a"].incoming_calls == 2
        assert scores["repo/svc.py::b"].hotness == 0.5
        assert scores["repo/svc.py::c"].hotness == 0.0

    def test_normalization_range(self):
        nodes = [_node("a"), _node("b")]
        edges = [_edge("repo/svc.py::b", "repo/svc.py::a")]
        scorer = HotPathScorer(nodes, edges)
        scores = scorer.score_nodes()
        for s in scores.values():
            assert 0.0 <= s.hotness <= 1.0

    def test_rank_nodes_ordering(self):
        nodes = [_node("a"), _node("b"), _node("c")]
        edges = [
            _edge("repo/svc.py::b", "repo/svc.py::a"),
            _edge("repo/svc.py::c", "repo/svc.py::a"),
            _edge("repo/svc.py::c", "repo/svc.py::b"),
        ]
        scorer = HotPathScorer(nodes, edges)
        ranked = scorer.rank_nodes([n.id for n in nodes])
        assert ranked[0] == "repo/svc.py::a"

    def test_rank_with_empty(self):
        nodes = [_node("a")]
        scorer = HotPathScorer(nodes, [])
        assert scorer.rank_nodes([]) == []

    def test_rank_with_missing_ids(self):
        nodes = [_node("a")]
        scorer = HotPathScorer(nodes, [])
        ranked = scorer.rank_nodes(["repo/svc.py::unknown"])
        assert ranked[0] == "repo/svc.py::unknown"

    def test_hot_edges_sorted(self):
        nodes = [_node("a"), _node("b"), _node("c")]
        edges = [
            _edge("repo/svc.py::b", "repo/svc.py::c"),
            _edge("repo/svc.py::b", "repo/svc.py::a"),
        ]
        scorer = HotPathScorer(nodes, [_edge("repo/svc.py::x", "repo/svc.py::a")])
        sorted_edges = scorer.get_hot_edges(edges)
        assert sorted_edges[0].target == "repo/svc.py::a"

    def test_persist_roundtrip(self, tmp_path: Path):
        nodes = [_node("a"), _node("b")]
        edges = [_edge("repo/svc.py::b", "repo/svc.py::a")]
        storage = GraphStorage(tmp_path)
        scorer = HotPathScorer(nodes, edges)
        scores = scorer.score_nodes()
        storage.save_hotpath(scores)
        loaded = storage.load_hotpath()
        assert loaded["repo/svc.py::a"].hotness == 1.0
        assert loaded["repo/svc.py::b"].hotness == 0.0

    def test_ignores_non_calls_edges(self):
        nodes = [_node("a"), _node("b")]
        edges = [
            SymbolEdge(source="repo/svc.py::b", target="repo/svc.py::a",
                       kind=EdgeKind.CONTAINS, confidence=1.0),
            SymbolEdge(source="repo/svc.py::b", target="repo/svc.py::a",
                       kind=EdgeKind.IMPORTS, confidence=0.95),
        ]
        scorer = HotPathScorer(nodes, edges)
        scores = scorer.score_nodes()
        assert scores["repo/svc.py::a"].incoming_calls == 0

    def test_uniform_graph(self):
        nodes = [_node("a"), _node("b")]
        edges = [
            _edge("repo/svc.py::a", "repo/svc.py::b"),
            _edge("repo/svc.py::b", "repo/svc.py::a"),
        ]
        scorer = HotPathScorer(nodes, edges)
        scores = scorer.score_nodes()
        assert scores["repo/svc.py::a"].hotness == 1.0
        assert scores["repo/svc.py::b"].hotness == 1.0

    def test_hotpath_in_retrieval(self):
        """Integration: RetrievalEngine loads hot-path and sorts nodes."""
        from kb_agent.query.composer import compose_context
        from kb_agent.query.expander import ExpandedSubgraph
        from kb_agent.query.intent import QueryIntent

        a = _node("hot_func", "svc.py", 1)
        b = _node("cold_func", "svc.py", 10)
        subgraph = ExpandedSubgraph(
            seed_nodes=[a, b],
            hop1_nodes=[],
            hop2_nodes=[],
        )
        hot = {"repo/svc.py::hot_func": 1.0, "repo/svc.py::cold_func": 0.2}
        result = compose_context(
            subgraph=subgraph,
            seed_entries=[],
            unmapped_entries=[],
            intent=QueryIntent.DEFAULT,
            hot_path_scores=hot,
        )
        lines = result.context.split("\n")
        hot_idx = next(i for i, l in enumerate(lines) if "hot_func" in l)
        cold_idx = next(i for i, l in enumerate(lines) if "cold_func" in l)
        assert hot_idx < cold_idx, "hot_func should appear before cold_func"
