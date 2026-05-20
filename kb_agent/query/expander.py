"""Bounded BFS graph expansion from seed nodes."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from kb_agent.graph.confidence import ConfidencePropagator
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
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
    hop3_nodes: list[SymbolNode] = field(default_factory=list)
    hop4_nodes: list[SymbolNode] = field(default_factory=list)
    relevant_edges: list[SymbolEdge] = field(default_factory=list)

    @property
    def all_nodes(self) -> list[SymbolNode]:
        return self.seed_nodes + self.hop1_nodes + self.hop2_nodes + self.hop3_nodes + self.hop4_nodes


def expand_from_seeds(
    seed_nodes: list[SymbolNode],
    mapper: ViewIDMapper,
    *,
    max_hops: int = MAX_HOPS,
    max_nodes: int = MAX_NODES,
    max_edges_per_node: int = MAX_EDGES_PER_NODE,
    min_confidence: float = MIN_CONFIDENCE,
    strategy: object | None = None,
    debug_log: list[str] | None = None,
) -> ExpandedSubgraph:
    """BFS expansion from seed nodes with bounded traversal.

    When a strategy is provided, its values override the default kwargs
    and edge-kind/direction filtering is applied.
    """
    if strategy is not None:
        max_hops = strategy.max_hops
        max_nodes = strategy.max_nodes
        max_edges_per_node = strategy.max_edges_per_node
        min_confidence = strategy.min_confidence

    included: dict[str, SymbolNode] = {}
    hop_of: dict[str, int] = {}
    edges: list[SymbolEdge] = []

    for node in seed_nodes[:max_nodes]:
        included[node.id] = node
        hop_of[node.id] = 0
        if debug_log is not None:
            debug_log.append(f"SEED: {node.id} ({node.name})")

    queue: deque[tuple[str, int]] = deque(
        (n.id, 0) for n in seed_nodes[:max_nodes]
    )

    while queue and len(included) < max_nodes:
        current_id, depth = queue.popleft()
        if depth >= max_hops:
            if debug_log is not None:
                debug_log.append(f"SKIP: {current_id} at depth {depth} >= max_hops {max_hops}")
            continue

        outgoing = mapper.edges_by_source.get(current_id, [])
        incoming = mapper.edges_by_target.get(current_id, [])

        # Apply direction filtering from strategy
        if strategy is not None and strategy.direction == "outgoing":
            candidates = _filter_edges(
                outgoing, mapper, min_confidence, max_edges_per_node, strategy, debug_log,
            )
        elif strategy is not None and strategy.direction == "incoming":
            candidates = _filter_edges(
                incoming, mapper, min_confidence, max_edges_per_node, strategy, debug_log,
            )
        else:
            candidates = _filter_edges(
                outgoing + incoming, mapper, min_confidence, max_edges_per_node, strategy, debug_log,
            )

        for edge in candidates:
            neighbor_id = (
                edge.target if edge.source == current_id else edge.source
            )

            if neighbor_id in included:
                edges.append(edge)
                if debug_log is not None:
                    debug_log.append(f"EDGE: {edge.source} --{edge.kind.value}--> {edge.target} (existing)")
                continue

            if len(included) >= max_nodes:
                if debug_log is not None:
                    debug_log.append(f"TRUNCATE: {neighbor_id} exceeded max_nodes {max_nodes}")
                break

            neighbor = mapper.node_by_id.get(neighbor_id)
            if neighbor is None:
                continue

            included[neighbor_id] = neighbor
            hop_of[neighbor_id] = depth + 1
            queue.append((neighbor_id, depth + 1))
            edges.append(edge)
            if debug_log is not None:
                debug_log.append(f"EXPAND: {neighbor_id} ({neighbor.name}) at hop {depth + 1} via {edge.kind.value}")

    # Apply hop-based confidence decay (query-time only)
    propagator = ConfidencePropagator(list(included.values()), edges)
    decayed_edges = propagator.apply_hop_decay(hop_of, edges)

    return ExpandedSubgraph(
        seed_nodes=[n for nid, n in included.items() if hop_of[nid] == 0],
        hop1_nodes=[n for nid, n in included.items() if hop_of[nid] == 1],
        hop2_nodes=[n for nid, n in included.items() if hop_of[nid] == 2],
        hop3_nodes=[n for nid, n in included.items() if hop_of[nid] == 3],
        hop4_nodes=[n for nid, n in included.items() if hop_of[nid] == 4],
        relevant_edges=decayed_edges,
    )


def _filter_edges(
    edges: list[SymbolEdge],
    mapper: ViewIDMapper,
    min_confidence: float,
    max_per_node: int,
    strategy: object | None = None,
    debug_log: list[str] | None = None,
) -> list[SymbolEdge]:
    """Filter by confidence + edge kind + utility suppression, keep top-N."""
    result: list[SymbolEdge] = []
    for edge in sorted(edges, key=lambda e: e.confidence, reverse=True):
        if edge.confidence < min_confidence:
            if debug_log is not None:
                debug_log.append(f"SUPPRESS: {edge.source}--{edge.kind.value}-->{edge.target} conf={edge.confidence:.2f} < {min_confidence}")
            continue
        if strategy is not None and edge.kind not in strategy.follow_edge_kinds:
            # Always allow BRIDGES_TO and REFERENCES_REPO through
            if edge.kind not in (EdgeKind.BRIDGES_TO, EdgeKind.REFERENCES_REPO):
                if debug_log is not None:
                    debug_log.append(f"SUPPRESS: {edge.source}--{edge.kind.value}-->{edge.target} edge kind not in strategy")
                continue
        if _is_utility_node(edge.source, mapper):
            if debug_log is not None:
                debug_log.append(f"SUPPRESS: {edge.source}--{edge.kind.value}-->{edge.target} source is utility")
            continue
        if _is_utility_node(edge.target, mapper):
            if debug_log is not None:
                debug_log.append(f"SUPPRESS: {edge.source}--{edge.kind.value}-->{edge.target} target is utility")
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
