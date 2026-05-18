"""Tests for query planner (Phase 2, Step 4)."""
from __future__ import annotations

import pytest

from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.query.intent import QueryIntent
from kb_agent.query.planner import ExpansionStrategy, QueryPlanner, STRATEGY_TABLE
from kb_agent.query.expander import expand_from_seeds
from kb_agent.views.base import ViewIDMapper


def _make_node(name: str, node_id: str | None = None) -> SymbolNode:
    return SymbolNode(
        id=node_id or f"repo/src/main.py::{name}()",
        name=name,
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        path="src/main.py",
        line_start=1,
        line_end=10,
    )


def _make_edge(
    source: str, target: str,
    kind: EdgeKind = EdgeKind.CALLS,
    confidence: float = 0.80,
) -> SymbolEdge:
    return SymbolEdge(
        source=source, target=target,
        kind=kind, confidence=confidence,
    )


class TestStrategyTable:
    def test_symbol_lookup_strategy(self):
        s = STRATEGY_TABLE[QueryIntent.SYMBOL_LOOKUP]
        assert s.max_hops == 1
        assert s.direction == "outgoing"
        assert EdgeKind.CALLS in s.follow_edge_kinds
        assert EdgeKind.CONTAINS in s.follow_edge_kinds
        assert s.max_nodes == 8

    def test_flow_trace_strategy(self):
        s = STRATEGY_TABLE[QueryIntent.FLOW_TRACE]
        assert s.max_hops == 3
        assert s.direction == "outgoing"
        assert s.follow_edge_kinds == (EdgeKind.CALLS,)

    def test_module_overview_strategy(self):
        s = STRATEGY_TABLE[QueryIntent.MODULE_OVERVIEW]
        assert s.direction == "bidirectional"
        assert EdgeKind.CONTAINS in s.follow_edge_kinds
        assert EdgeKind.IMPORTS in s.follow_edge_kinds
        assert s.max_nodes == 20

    def test_relationship_strategy(self):
        s = STRATEGY_TABLE[QueryIntent.RELATIONSHIP]
        assert s.direction == "incoming"
        assert EdgeKind.CALLS in s.follow_edge_kinds
        assert EdgeKind.IMPORTS in s.follow_edge_kinds

    def test_default_strategy(self):
        s = STRATEGY_TABLE[QueryIntent.DEFAULT]
        assert s.max_hops == 2
        assert s.direction == "bidirectional"
        assert s.max_nodes == 15


class TestQueryPlanner:
    def test_plan_returns_correct_strategy(self):
        planner = QueryPlanner()
        strategy = planner.plan(QueryIntent.FLOW_TRACE)
        assert strategy.max_hops == 3
        assert strategy.direction == "outgoing"

    def test_plan_unknown_intent_returns_default(self):
        planner = QueryPlanner()
        strategy = planner.plan(QueryIntent.DEFAULT)
        assert strategy.max_hops == 2


class TestStrategyIntegration:
    def test_flow_trace_follows_calls_chain(self):
        """FLOW_TRACE strategy should follow a 3-hop call chain."""
        a = _make_node("a", "a")
        b = _make_node("b", "b")
        c = _make_node("c", "c")
        d = _make_node("d", "d")
        edges = [
            _make_edge("a", "b"),
            _make_edge("b", "c"),
            _make_edge("c", "d"),
        ]
        mapper = ViewIDMapper([a, b, c, d], edges)
        strategy = STRATEGY_TABLE[QueryIntent.FLOW_TRACE]
        subgraph = expand_from_seeds([a], mapper, strategy=strategy)
        # With 3 hops and outgoing only, should reach b, c, d
        all_ids = {n.id for n in subgraph.all_nodes}
        assert "d" in all_ids
        assert [n.id for n in subgraph.hop2_nodes] == ["c"]
        assert [n.id for n in subgraph.hop3_nodes] == ["d"]

    def test_relationship_finds_callers(self):
        """RELATIONSHIP strategy should find incoming callers."""
        target = _make_node("target", "target")
        caller_a = _make_node("caller_a", "caller_a")
        caller_b = _make_node("caller_b", "caller_b")
        edges = [
            _make_edge("caller_a", "target"),
            _make_edge("caller_b", "target"),
        ]
        mapper = ViewIDMapper([target, caller_a, caller_b], edges)
        strategy = STRATEGY_TABLE[QueryIntent.RELATIONSHIP]
        subgraph = expand_from_seeds([target], mapper, strategy=strategy)
        # Incoming-only should find caller_a and caller_b
        all_ids = {n.id for n in subgraph.all_nodes}
        assert "caller_a" in all_ids
        assert "caller_b" in all_ids
        assert {edge.confidence for edge in subgraph.relevant_edges} == {0.64}

    def test_no_strategy_backward_compat(self):
        """Without strategy, behavior should be same as before."""
        a = _make_node("a", "a")
        b = _make_node("b", "b")
        edges = [_make_edge("a", "b")]
        mapper = ViewIDMapper([a, b], edges)
        subgraph = expand_from_seeds([a], mapper)
        all_ids = {n.id for n in subgraph.all_nodes}
        assert "a" in all_ids
        assert "b" in all_ids

    def test_symbol_lookup_limits_to_1_hop(self):
        """SYMBOL_LOOKUP should stop at 1 hop."""
        a = _make_node("a", "a")
        b = _make_node("b", "b")
        c = _make_node("c", "c")
        edges = [
            _make_edge("a", "b"),
            _make_edge("b", "c"),
        ]
        mapper = ViewIDMapper([a, b, c], edges)
        strategy = STRATEGY_TABLE[QueryIntent.SYMBOL_LOOKUP]
        subgraph = expand_from_seeds([a], mapper, strategy=strategy)
        all_ids = {n.id for n in subgraph.all_nodes}
        assert "b" in all_ids
        assert "c" not in all_ids  # 2nd hop excluded

    def test_edge_kind_filtering(self):
        """Strategy filters by edge kind."""
        a = _make_node("a", "a")
        b = _make_node("b", "b")
        edges = [
            _make_edge("a", "b", kind=EdgeKind.IMPORTS, confidence=0.95),
        ]
        mapper = ViewIDMapper([a, b], edges)
        # FLOW_TRACE only follows CALLS edges
        strategy = STRATEGY_TABLE[QueryIntent.FLOW_TRACE]
        subgraph = expand_from_seeds([a], mapper, strategy=strategy)
        # IMPORTS edge should be filtered out
        assert len(subgraph.all_nodes) == 1  # Only seed
