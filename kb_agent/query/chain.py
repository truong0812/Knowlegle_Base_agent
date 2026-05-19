"""Causal chain detection — walk CALLS edges to produce ordered execution chains."""
from __future__ import annotations

from dataclasses import dataclass, field

from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.views.base import ViewIDMapper


@dataclass
class CallChain:
    nodes: list[str]  # ordered node IDs in the chain
    edges: list[str]  # edge descriptions
    length: int


class CausalChainDetector:
    """Detect call chains from an expanded subgraph."""

    def __init__(
        self,
        mapper: ViewIDMapper,
        hot_path_scores: dict[str, float] | None = None,
    ) -> None:
        self._mapper = mapper
        self._hotpath = hot_path_scores or {}

    def detect_chains(
        self,
        seed_ids: list[str],
        included_nodes: dict[str, SymbolNode],
        edges: list[SymbolEdge],
        min_length: int = 2,
        max_chains: int = 5,
    ) -> list[CallChain]:
        """Walk CALLS edges from seeds to produce ordered chains.

        Only follows outgoing CALLS edges through nodes in included_nodes.
        """
        node_set = set(included_nodes.keys())
        calls_by_source: dict[str, list[SymbolEdge]] = {}
        for e in edges:
            if e.kind == EdgeKind.CALLS:
                calls_by_source.setdefault(e.source, []).append(e)

        chains: list[CallChain] = []
        for seed_id in seed_ids:
            self._walk(seed_id, node_set, calls_by_source, [seed_id], [], chains, min_length)
            if len(chains) >= max_chains:
                break

        # Sort by (length desc, hotness of chain desc)
        chains.sort(
            key=lambda c: (c.length, self._chain_hotness(c)),
            reverse=True,
        )
        return self._merge_chains(chains, max_chains)

    def _walk(
        self,
        current: str,
        node_set: set[str],
        calls_by_source: dict[str, list[SymbolEdge]],
        path: list[str],
        edge_path: list[str],
        results: list[CallChain],
        min_length: int,
        visited: set[str] | None = None,
    ) -> None:
        if visited is None:
            visited = set()
        if current in visited:
            return
        visited.add(current)

        outgoing = calls_by_source.get(current, [])
        # Sort outgoing by target hotness for deterministic ordering
        outgoing = sorted(
            outgoing,
            key=lambda e: self._hotpath.get(e.target, 0.0),
            reverse=True,
        )

        for edge in outgoing:
            if edge.target not in node_set or edge.target in visited:
                continue
            new_path = path + [edge.target]
            new_edge_path = edge_path + [f"{edge.source}--{edge.kind.value}-->{edge.target}"]

            if len(new_path) >= min_length:
                results.append(CallChain(
                    nodes=list(new_path),
                    edges=list(new_edge_path),
                    length=len(new_path),
                ))

            if len(new_path) < 8:  # prevent infinite walks
                self._walk(edge.target, node_set, calls_by_source, new_path, new_edge_path, results, min_length, set(visited))

    def _chain_hotness(self, chain: CallChain) -> float:
        if not self._hotpath:
            return 0.0
        return sum(self._hotpath.get(nid, 0.0) for nid in chain.nodes) / len(chain.nodes)

    def _merge_chains(self, chains: list[CallChain], max_chains: int) -> list[CallChain]:
        """Deduplicate chains with identical node sequences."""
        seen: set[tuple[str, ...]] = set()
        result: list[CallChain] = []
        for chain in chains:
            key = tuple(chain.nodes)
            if key not in seen:
                seen.add(key)
                result.append(chain)
            if len(result) >= max_chains:
                break
        return result
