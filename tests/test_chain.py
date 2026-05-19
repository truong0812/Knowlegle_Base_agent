"""Tests for causal chain detection and CHAIN_TRACE intent."""
from __future__ import annotations

from pathlib import Path

import pytest

from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.query.chain import CallChain, CausalChainDetector
from kb_agent.query.expander import ExpandedSubgraph, expand_from_seeds
from kb_agent.query.intent import QueryIntent, classify_intent
from kb_agent.query.planner import QueryPlanner
from kb_agent.views.base import ViewIDMapper


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


def _build_mapper(
    nodes: list[SymbolNode], edges: list[SymbolEdge],
) -> ViewIDMapper:
    return ViewIDMapper(nodes, edges)


class TestCausalChainDetector:
    def test_detect_simple_chain(self):
        a, b, c = _node("a"), _node("b"), _node("c")
        edges = [_edge(a.id, b.id), _edge(b.id, c.id)]
        mapper = _build_mapper([a, b, c], edges)
        detector = CausalChainDetector(mapper)
        included = {n.id: n for n in [a, b, c]}
        chains = detector.detect_chains([a.id], included, edges, min_length=2)
        assert len(chains) > 0
        # Longest chain should be a -> b -> c (length 3)
        assert any(ch.length == 3 for ch in chains)

    def test_detect_multiple_chains(self):
        a, b, c, d = _node("a"), _node("b"), _node("c"), _node("d")
        edges = [_edge(a.id, b.id), _edge(a.id, c.id), _edge(b.id, d.id)]
        mapper = _build_mapper([a, b, c, d], edges)
        detector = CausalChainDetector(mapper)
        included = {n.id: n for n in [a, b, c, d]}
        chains = detector.detect_chains([a.id], included, edges, min_length=2)
        assert len(chains) >= 2

    def test_min_length_filter(self):
        a, b = _node("a"), _node("b")
        edges = [_edge(a.id, b.id)]
        mapper = _build_mapper([a, b], edges)
        detector = CausalChainDetector(mapper)
        included = {n.id: n for n in [a, b]}
        chains = detector.detect_chains([a.id], included, edges, min_length=3)
        assert len(chains) == 0

    def test_merge_overlapping_chains(self):
        a, b, c = _node("a"), _node("b"), _node("c")
        edges = [_edge(a.id, b.id), _edge(b.id, c.id)]
        mapper = _build_mapper([a, b, c], edges)
        detector = CausalChainDetector(mapper)
        included = {n.id: n for n in [a, b, c]}
        chains = detector.detect_chains([a.id], included, edges, min_length=2)
        # Should not have duplicate chains with same node sequence
        node_seqs = [tuple(ch.nodes) for ch in chains]
        assert len(node_seqs) == len(set(node_seqs))

    def test_chain_ordering_by_length(self):
        a, b, c, d = _node("a"), _node("b"), _node("c"), _node("d")
        edges = [_edge(a.id, b.id), _edge(b.id, c.id), _edge(c.id, d.id)]
        mapper = _build_mapper([a, b, c, d], edges)
        detector = CausalChainDetector(mapper)
        included = {n.id: n for n in [a, b, c, d]}
        chains = detector.detect_chains([a.id], included, edges, min_length=2)
        if len(chains) > 1:
            assert chains[0].length >= chains[1].length

    def test_chain_ordering_by_hotness(self):
        a, b, c = _node("a"), _node("b"), _node("c")
        edges = [_edge(a.id, b.id), _edge(a.id, c.id)]
        mapper = _build_mapper([a, b, c], edges)
        hot = {a.id: 0.5, b.id: 1.0, c.id: 0.2}
        detector = CausalChainDetector(mapper, hot_path_scores=hot)
        included = {n.id: n for n in [a, b, c]}
        chains = detector.detect_chains([a.id], included, edges, min_length=2)
        if len(chains) > 1:
            # Chains with higher hotness should come first when lengths equal
            assert chains[0].nodes[1] == b.id

    def test_empty_subgraph_no_chains(self):
        a = _node("a")
        mapper = _build_mapper([a], [])
        detector = CausalChainDetector(mapper)
        chains = detector.detect_chains([a.id], {a.id: a}, [], min_length=2)
        assert len(chains) == 0

    def test_chain_trace_intent(self):
        assert classify_intent("call chain from login to save") == QueryIntent.CHAIN_TRACE
        assert classify_intent("causal chain of authentication") == QueryIntent.CHAIN_TRACE
        assert classify_intent("trace from request to response") == QueryIntent.CHAIN_TRACE
        assert classify_intent("full path from login") == QueryIntent.CHAIN_TRACE

    def test_chain_trace_strategy(self):
        planner = QueryPlanner()
        strategy = planner.plan(QueryIntent.CHAIN_TRACE)
        assert strategy.max_hops == 4
        assert strategy.max_nodes == 25
        assert strategy.direction == "outgoing"
        assert EdgeKind.CALLS in strategy.follow_edge_kinds

    def test_compose_with_chains(self):
        from kb_agent.query.composer import compose_context
        a, b, c = _node("a"), _node("b"), _node("c")
        subgraph = ExpandedSubgraph(seed_nodes=[a], hop1_nodes=[b], hop2_nodes=[c])
        chains = [CallChain(nodes=[a.id, b.id, c.id], edges=[], length=3)]
        result = compose_context(
            subgraph=subgraph,
            seed_entries=[],
            unmapped_entries=[],
            intent=QueryIntent.CHAIN_TRACE,
            chains=chains,
        )
        assert "CALL CHAINS" in result.context
        assert "a" in result.context

    def test_chain_budget_allocation(self):
        from kb_agent.query.composer import compose_context
        from kb_agent.query.intent import INTENT_BUDGET_RATIOS
        ratios = INTENT_BUDGET_RATIOS[QueryIntent.CHAIN_TRACE]
        assert "chain" in ratios
        assert ratios["chain"] > 0
