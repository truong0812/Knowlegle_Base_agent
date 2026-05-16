"""Tests for confidence propagation (Phase 2, Step 2)."""
from __future__ import annotations

import pytest

from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.graph.confidence import (
    ConfidencePropagator,
    HOP_DECAY_FACTORS,
    HIGH_CONFIDENCE_THRESHOLD,
    EDGE_BONUS_MIN_EDGES,
    EDGE_BONUS_FACTOR,
    MAX_EDGE_BONUS,
)


def _make_node(
    name: str = "func",
    node_id: str | None = None,
    confidence: float = 1.0,
) -> SymbolNode:
    return SymbolNode(
        id=node_id or f"repo/src/main.py::{name}()",
        name=name,
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        path="src/main.py",
        line_start=1,
        line_end=10,
        confidence=confidence,
    )


def _make_edge(
    source: str = "repo/src/a.py::a()",
    target: str = "repo/src/b.py::b()",
    confidence: float = 0.80,
    kind: EdgeKind = EdgeKind.CALLS,
) -> SymbolEdge:
    return SymbolEdge(
        source=source,
        target=target,
        kind=kind,
        confidence=confidence,
        source_type="heuristic",
        resolution="direct_import",
    )


class TestNodeConfidence:
    def test_base_confidence_deterministic(self):
        """Nodes with no incoming edges keep their default confidence."""
        node = _make_node("handler")
        propagator = ConfidencePropagator([node], [])
        result = propagator.compute_node_confidences()
        assert result[node.id].base_confidence == 1.0
        assert result[node.id].edge_bonus == 0.0
        assert result[node.id].propagated_confidence == 1.0

    def test_edge_bonus_with_3_high_confidence_edges(self):
        """Node with 3+ high-confidence incoming edges gets a boost."""
        target = _make_node("target")
        edges = [
            _make_edge(source=f"src/a{i}", target=target.id, confidence=0.80)
            for i in range(3)
        ]
        propagator = ConfidencePropagator([target], edges)
        result = propagator.compute_node_confidences()
        assert result[target.id].edge_bonus > 0.0
        expected_bonus = min(3 * EDGE_BONUS_FACTOR, MAX_EDGE_BONUS)
        # Confidence capped at 1.0
        assert result[target.id].propagated_confidence == pytest.approx(1.0)

    def test_edge_bonus_capped(self):
        """Edge bonus does not exceed MAX_EDGE_BONUS."""
        target = _make_node("target")
        edges = [
            _make_edge(source=f"src/a{i}", target=target.id, confidence=0.90)
            for i in range(20)
        ]
        propagator = ConfidencePropagator([target], edges)
        result = propagator.compute_node_confidences()
        assert result[target.id].edge_bonus <= MAX_EDGE_BONUS
        assert result[target.id].propagated_confidence <= 1.0

    def test_no_bonus_below_threshold(self):
        """Node with < 3 high-confidence edges gets no bonus."""
        target = _make_node("target")
        edges = [
            _make_edge(source="src/a1", target=target.id, confidence=0.50),
            _make_edge(source="src/a2", target=target.id, confidence=0.60),
        ]
        propagator = ConfidencePropagator([target], edges)
        result = propagator.compute_node_confidences()
        assert result[target.id].edge_bonus == 0.0

    def test_only_high_confidence_edges_count(self):
        """Edges below HIGH_CONFIDENCE_THRESHOLD don't count toward bonus."""
        target = _make_node("target")
        edges = [
            _make_edge(source=f"src/a{i}", target=target.id, confidence=0.50)
            for i in range(5)
        ]
        propagator = ConfidencePropagator([target], edges)
        result = propagator.compute_node_confidences()
        assert result[target.id].edge_bonus == 0.0

    def test_backward_compatible_default_confidence(self):
        """SymbolNode default confidence is 1.0 (backward compat)."""
        node = SymbolNode(
            id="repo/test.py::foo()",
            name="foo",
            kind=SymbolKind.FUNCTION,
            language=Language.PYTHON,
            path="test.py",
            line_start=1,
            line_end=5,
        )
        assert node.confidence == 1.0


class TestEdgeConfidence:
    def test_hop_0_no_decay(self):
        """Hop 0 edges keep full confidence."""
        node = _make_node("b")
        edge = _make_edge(confidence=0.80, target=node.id)
        propagator = ConfidencePropagator([node], [edge])
        result = propagator.compute_edge_confidences({node.id: 0})
        assert result[0].effective_confidence == pytest.approx(0.80)

    def test_hop_1_decay(self):
        """Hop 1 edges get 0.8x confidence."""
        node = _make_node("b")
        edge = _make_edge(confidence=0.80, target=node.id)
        propagator = ConfidencePropagator([node], [edge])
        result = propagator.compute_edge_confidences({node.id: 1})
        assert result[0].decay_factor == 0.8
        assert result[0].effective_confidence == pytest.approx(0.64)

    def test_incoming_edge_uses_farthest_endpoint_hop(self):
        """Incoming caller edges decay by caller hop, not by seed target hop."""
        edge = _make_edge(source="caller", target="target", confidence=0.80)
        propagator = ConfidencePropagator([], [edge])
        result = propagator.compute_edge_confidences({"target": 0, "caller": 1})
        assert result[0].hop == 1
        assert result[0].effective_confidence == pytest.approx(0.64)

    def test_hop_2_decay(self):
        """Hop 2 edges get 0.6x confidence."""
        node = _make_node("b")
        edge = _make_edge(confidence=0.80, target=node.id)
        propagator = ConfidencePropagator([node], [edge])
        result = propagator.compute_edge_confidences({node.id: 2})
        assert result[0].decay_factor == 0.6
        assert result[0].effective_confidence == pytest.approx(0.48)

    def test_hop_decay_factors_table(self):
        """Verify the decay factor lookup table."""
        assert HOP_DECAY_FACTORS[0] == 1.0
        assert HOP_DECAY_FACTORS[1] == 0.8
        assert HOP_DECAY_FACTORS[2] == 0.6


class TestApplyHopDecay:
    def test_creates_copies(self):
        """apply_hop_decay does NOT modify original edges."""
        node = _make_node("b")
        edge = _make_edge(confidence=0.80, target=node.id)
        original_conf = edge.confidence
        propagator = ConfidencePropagator([node], [edge])
        decayed = propagator.apply_hop_decay({node.id: 1}, [edge])
        assert edge.confidence == original_conf  # Original unchanged
        assert decayed[0].confidence < original_conf  # Decayed is different

    def test_mixed_hops(self):
        """Edges to different hop distances get different decay."""
        node_a = _make_node("a", node_id="a")
        node_b = _make_node("b", node_id="b")
        node_c = _make_node("c", node_id="c")
        edge_ab = _make_edge(source="a", target="b", confidence=1.0)
        edge_ac = _make_edge(source="a", target="c", confidence=1.0)
        propagator = ConfidencePropagator(
            [node_a, node_b, node_c], [edge_ab, edge_ac],
        )
        decayed = propagator.apply_hop_decay({"b": 0, "c": 2}, [edge_ab, edge_ac])
        assert decayed[0].confidence == pytest.approx(1.0)  # hop 0
        assert decayed[1].confidence == pytest.approx(0.6)  # hop 2

    def test_apply_hop_decay_for_incoming_edge(self):
        edge = _make_edge(source="caller", target="target", confidence=1.0)
        propagator = ConfidencePropagator([], [edge])
        decayed = propagator.apply_hop_decay(
            {"target": 0, "caller": 1}, [edge],
        )
        assert decayed[0].confidence == pytest.approx(0.8)


class TestBuildTimePropagation:
    def test_node_confidence_propagated_in_build(self):
        """GraphBuilder propagates node confidence after building."""
        from kb_agent.graph.builder import GraphBuilder
        from kb_agent.parser.base import CallInfo, ParseResult, SymbolInfo

        # Create a target function with many callers
        target = SymbolInfo(
            name="validate", kind=SymbolKind.FUNCTION, line_start=1, line_end=5,
        )
        callers = [
            SymbolInfo(
                name=f"caller_{i}", kind=SymbolKind.FUNCTION,
                line_start=10 + i * 10, line_end=15 + i * 10,
            )
            for i in range(4)
        ]
        calls = [
            CallInfo(
                caller_name=f"caller_{i}", callee_name="validate",
                line=12 + i * 10, resolution_method="same_file",
            )
            for i in range(4)
        ]

        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "src/main.py": ParseResult(
                file_path="src/main.py",
                language=Language.PYTHON,
                symbols=[target] + callers,
                calls=calls,
            ),
        })

        validate_node = [n for n in builder.nodes if n.name == "validate"][0]
        # Confidence is capped at 1.0 but the propagation ran successfully
        assert validate_node.confidence == 1.0
        # Verify CALLS edges exist (4 callers)
        calls_edges = [e for e in builder.edges if e.kind == EdgeKind.CALLS]
        assert len(calls_edges) == 4
