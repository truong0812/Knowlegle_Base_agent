"""Bounded BFS graph expansion from seed nodes."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from kb_agent.models.graph import SymbolEdge, SymbolNode
from kb_agent.views.base import ViewIDMapper

MAX_HOPS = 2
MAX_NODES = 15
MAX_EDGES_PER_NODE = 5
MIN_CONFIDENCE = 0.60


@dataclass
class ExpandedSubgraph:
    seed_nodes: list[SymbolNode]
    hop1_nodes: list[SymbolNode]
    hop2_nodes: list[SymbolNode]
    relevant_edges: list[SymbolEdge] = field(default_factory=list)

    @property
    def all_nodes(self) -> list[SymbolNode]:
        return self.seed_nodes + self.hop1_nodes + self.hop2_nodes


def expand_from_seeds(
    seed_nodes: list[SymbolNode],
    mapper: ViewIDMapper,
    *,
    max_hops: int = MAX_HOPS,
    max_nodes: int = MAX_NODES,
    max_edges_per_node: int = MAX_EDGES_PER_NODE,
    min_confidence: float = MIN_CONFIDENCE,
) -> ExpandedSubgraph:
    """BFS expansion from seed nodes with bounded traversal."""
    included: dict[str, SymbolNode] = {}
    hop_of: dict[str, int] = {}
    edges: list[SymbolEdge] = []

    for node in seed_nodes[:max_nodes]:
        included[node.id] = node
        hop_of[node.id] = 0

    queue: deque[tuple[str, int]] = deque(
        (n.id, 0) for n in seed_nodes[:max_nodes]
    )

    while queue and len(included) < max_nodes:
        current_id, depth = queue.popleft()
        if depth >= max_hops:
            continue

        outgoing = mapper.edges_by_source.get(current_id, [])
        incoming = mapper.edges_by_target.get(current_id, [])
        candidates = _filter_edges(
            outgoing + incoming, mapper, min_confidence, max_edges_per_node,
        )

        for edge in candidates:
            neighbor_id = (
                edge.target if edge.source == current_id else edge.source
            )

            if neighbor_id in included:
                # Both endpoints are in the subgraph — record the edge
                edges.append(edge)
                continue

            if len(included) >= max_nodes:
                # Neighbor won't be included — skip edge to avoid
                # referencing a node absent from the composed context
                break

            neighbor = mapper.node_by_id.get(neighbor_id)
            if neighbor is None:
                continue

            included[neighbor_id] = neighbor
            hop_of[neighbor_id] = depth + 1
            queue.append((neighbor_id, depth + 1))
            edges.append(edge)

    return ExpandedSubgraph(
        seed_nodes=[n for nid, n in included.items() if hop_of[nid] == 0],
        hop1_nodes=[n for nid, n in included.items() if hop_of[nid] == 1],
        hop2_nodes=[n for nid, n in included.items() if hop_of[nid] == 2],
        relevant_edges=edges,
    )


def _filter_edges(
    edges: list[SymbolEdge],
    mapper: ViewIDMapper,
    min_confidence: float,
    max_per_node: int,
) -> list[SymbolEdge]:
    """Filter by confidence + utility suppression, keep top-N by confidence."""
    result: list[SymbolEdge] = []
    for edge in sorted(edges, key=lambda e: e.confidence, reverse=True):
        if edge.confidence < min_confidence:
            continue
        if _is_utility_node(edge.source, mapper):
            continue
        if _is_utility_node(edge.target, mapper):
            continue
        result.append(edge)
        if len(result) >= max_per_node:
            break
    return result


def _is_utility_node(node_id: str, mapper: ViewIDMapper) -> bool:
    node = mapper.node_by_id.get(node_id)
    if node is None:
        return False
    return ViewIDMapper.is_utility_name(node.name)
