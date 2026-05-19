"""Hot-path scoring: rank nodes by incoming call frequency."""
from __future__ import annotations

from dataclasses import dataclass

from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode


@dataclass
class HotPathScore:
    node_id: str
    incoming_calls: int
    hotness: float  # normalized 0.0–1.0


class HotPathScorer:
    """Computes hot-path scores from CALLS edges."""

    def __init__(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
    ) -> None:
        self._nodes = nodes
        self._edges = edges

    def score_nodes(self) -> dict[str, HotPathScore]:
        """Compute hot-path scores for all nodes.

        hotness = normalized incoming CALLS count using min-max scaling.
        Nodes with zero incoming calls get hotness 0.0.
        """
        incoming: dict[str, int] = {}
        for edge in self._edges:
            if edge.kind == EdgeKind.CALLS:
                incoming[edge.target] = incoming.get(edge.target, 0) + 1

        max_calls = max(incoming.values()) if incoming else 0

        scores: dict[str, HotPathScore] = {}
        for node in self._nodes:
            count = incoming.get(node.id, 0)
            hotness = count / max_calls if max_calls > 0 else 0.0
            scores[node.id] = HotPathScore(
                node_id=node.id,
                incoming_calls=count,
                hotness=round(hotness, 4),
            )
        return scores

    def rank_nodes(self, node_ids: list[str]) -> list[str]:
        """Return node IDs sorted by hotness descending.

        Unknown IDs receive hotness 0.0.
        """
        scores = self.score_nodes()
        return sorted(
            node_ids,
            key=lambda nid: scores.get(nid, HotPathScore(nid, 0, 0.0)).hotness,
            reverse=True,
        )

    def get_hot_edges(
        self,
        edges: list[SymbolEdge],
        scores: dict[str, HotPathScore] | None = None,
    ) -> list[SymbolEdge]:
        """Return edges sorted by target hotness descending."""
        if scores is None:
            scores = self.score_nodes()
        return sorted(
            edges,
            key=lambda e: scores.get(e.target, HotPathScore(e.target, 0, 0.0)).hotness,
            reverse=True,
        )
