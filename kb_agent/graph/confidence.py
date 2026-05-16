"""Confidence propagation for symbol graph nodes and edges.

Computes:
- Node confidence: base (1.0 for deterministic) + edge bonus for well-connected nodes
- Edge confidence: hop-based decay for query-time expansion
"""
from __future__ import annotations

from dataclasses import dataclass

from kb_agent.models.graph import SymbolEdge, SymbolNode

# Hop decay factors applied at query-time
HOP_DECAY_FACTORS: dict[int, float] = {
    0: 1.0,
    1: 0.8,
    2: 0.6,
}

# Node confidence boost parameters
HIGH_CONFIDENCE_THRESHOLD = 0.70
EDGE_BONUS_MIN_EDGES = 3
EDGE_BONUS_FACTOR = 0.10
MAX_EDGE_BONUS = 0.30


@dataclass
class NodeConfidence:
    node_id: str
    base_confidence: float
    edge_bonus: float
    propagated_confidence: float


@dataclass
class EdgeConfidence:
    edge_index: int
    base_confidence: float
    hop: int
    decay_factor: float
    effective_confidence: float


class ConfidencePropagator:
    """Computes propagated confidence scores for nodes and edges."""

    def __init__(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
    ) -> None:
        self._nodes = nodes
        self._edges = edges

    def compute_node_confidences(self) -> dict[str, NodeConfidence]:
        """Compute propagated confidence for all nodes.

        Node confidence = base_confidence × (1 + edge_bonus), capped at 1.0.
        edge_bonus = min(high_conf_incoming_count × EDGE_BONUS_FACTOR, MAX_EDGE_BONUS)
        Only applied when node has >= EDGE_BONUS_MIN_EDGES high-confidence incoming edges.
        """
        incoming_by_target: dict[str, list[SymbolEdge]] = {}
        for edge in self._edges:
            incoming_by_target.setdefault(edge.target, []).append(edge)

        result: dict[str, NodeConfidence] = {}
        for node in self._nodes:
            base = node.confidence  # Default 1.0 from SymbolNode
            incoming = incoming_by_target.get(node.id, [])
            high_conf_count = sum(
                1 for e in incoming if e.confidence >= HIGH_CONFIDENCE_THRESHOLD
            )
            edge_bonus = 0.0
            if high_conf_count >= EDGE_BONUS_MIN_EDGES:
                edge_bonus = min(
                    high_conf_count * EDGE_BONUS_FACTOR, MAX_EDGE_BONUS,
                )
            propagated = min(base * (1 + edge_bonus), 1.0)
            result[node.id] = NodeConfidence(
                node_id=node.id,
                base_confidence=base,
                edge_bonus=edge_bonus,
                propagated_confidence=propagated,
            )
        return result

    def compute_edge_confidences(
        self,
        hop_map: dict[str, int],
    ) -> dict[int, EdgeConfidence]:
        """Compute effective confidence for edges based on target hop distance.

        Applied at query-time only — does NOT modify persisted graph.
        effective = base × HOP_DECAY_FACTORS[min(hop, 2)]
        """
        result: dict[int, EdgeConfidence] = {}
        for i, edge in enumerate(self._edges):
            hop = max(hop_map.get(edge.source, 0), hop_map.get(edge.target, 0))
            decay = HOP_DECAY_FACTORS.get(min(hop, 2), 0.6)
            effective = edge.confidence * decay
            result[i] = EdgeConfidence(
                edge_index=i,
                base_confidence=edge.confidence,
                hop=hop,
                decay_factor=decay,
                effective_confidence=effective,
            )
        return result

    def apply_hop_decay(
        self,
        hop_map: dict[str, int],
        edges: list[SymbolEdge],
    ) -> list[SymbolEdge]:
        """Return new edge list with hop-decayed confidence.

        Creates copies — does NOT modify original edges.
        """
        decayed: list[SymbolEdge] = []
        for edge in edges:
            hop = max(hop_map.get(edge.source, 0), hop_map.get(edge.target, 0))
            decay = HOP_DECAY_FACTORS.get(min(hop, 2), 0.6)
            decayed.append(SymbolEdge(
                source=edge.source,
                target=edge.target,
                kind=edge.kind,
                confidence=round(edge.confidence * decay, 4),
                source_type=edge.source_type,
                resolution=edge.resolution,
            ))
        return decayed
