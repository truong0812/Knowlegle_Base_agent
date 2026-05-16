"""Deterministic feature extraction from symbol names.

Clusters symbols by shared nouns, producing reproducible feature groups
that are identical across runs (no LLM, no randomness).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.views.base import ViewIDMapper

# Split snake_case and camelCase into words
_WORD_SPLIT = re.compile(r"([A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$))")

STOP_WORDS = frozenset({
    "get", "set", "is", "has", "do", "make", "run", "call", "new", "old",
    "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "with",
    "from", "init", "main", "process", "handle", "execute", "create",
    "update", "delete", "add", "remove", "check", "validate", "load",
    "save", "read", "write", "send", "receive", "start", "stop", "open",
    "close", "begin", "end", "put", "post", "patch", "head", "option",
    "list", "find", "search", "filter", "sort", "count", "print", "log",
    "test", "mock", "stub", "setup", "teardown", "self", "cls", "none",
    "true", "false", "data", "info", "item", "obj", "ctx", "arg", "kw",
    "result", "value", "key", "name", "type", "len", "str", "int", "bool",
    "float", "list", "dict", "tuple", "bytes", "error", "exception",
})

MIN_NOUN_LENGTH = 3
MERGE_OVERLAP_THRESHOLD = 0.50


@dataclass
class Feature:
    id: str
    name: str
    member_node_ids: list[str]
    naming_basis: str
    edge_density: int


class FeatureExtractor:
    """Deterministic feature extraction from symbol names."""

    def __init__(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
    ) -> None:
        self._nodes = nodes
        self._edges = edges

        # Pre-build edge adjacency for density computation
        self._edge_set: set[tuple[str, str]] = set()
        for edge in edges:
            self._edge_set.add((edge.source, edge.target))
            self._edge_set.add((edge.target, edge.source))

        # Node ID set for membership checks
        self._node_ids: set[str] = {n.id for n in nodes}

    def extract_nouns(self, name: str) -> list[str]:
        """Extract meaningful nouns from a symbol name.

        Splits on snake_case and camelCase boundaries,
        filters stop words and short tokens.
        """
        # Replace underscores with spaces for splitting
        normalized = name.replace("_", " ")
        words = _WORD_SPLIT.findall(normalized)
        return [
            w.lower() for w in words
            if len(w) >= MIN_NOUN_LENGTH and w.lower() not in STOP_WORDS
        ]

    def build_noun_to_nodes(self) -> dict[str, list[str]]:
        """Build noun → [node_ids] reverse index. Only nouns appearing in 2+ nodes."""
        noun_map: dict[str, list[str]] = {}
        for node in self._nodes:
            if ViewIDMapper.is_utility_name(node.name):
                continue
            nouns = self.extract_nouns(node.name)
            for noun in nouns:
                noun_map.setdefault(noun, []).append(node.id)

        # Filter: only keep nouns with 2+ nodes
        return {k: v for k, v in noun_map.items() if len(v) >= 2}

    def cluster_by_shared_nouns(self, noun_map: dict[str, list[str]]) -> list[Feature]:
        """Create candidate features from nouns with 2+ member nodes."""
        features: list[Feature] = []
        for noun, node_ids in sorted(noun_map.items()):
            density = self._compute_edge_density(node_ids)
            if density == 0:
                continue  # No structural connection
            features.append(Feature(
                id=f"feature.{noun}",
                name=noun,
                member_node_ids=node_ids,
                naming_basis=noun,
                edge_density=density,
            ))
        return features

    def merge_overlapping(self, features: list[Feature]) -> list[Feature]:
        """Merge features with Jaccard overlap >= threshold."""
        if not features:
            return []

        merged = list(features)
        changed = True
        while changed:
            changed = False
            result: list[Feature] = []
            used: set[int] = set()

            for i, a in enumerate(merged):
                if i in used:
                    continue
                current = a
                for j in range(i + 1, len(merged)):
                    if j in used:
                        continue
                    b = merged[j]
                    overlap = self._jaccard(
                        set(current.member_node_ids),
                        set(b.member_node_ids),
                    )
                    if overlap >= MERGE_OVERLAP_THRESHOLD:
                        # Merge b into current
                        combined = list(set(current.member_node_ids + b.member_node_ids))
                        density = self._compute_edge_density(combined)
                        # Keep the name with higher edge density
                        naming = current.naming_basis if current.edge_density >= b.edge_density else b.naming_basis
                        current = Feature(
                            id=f"feature.{naming}",
                            name=naming,
                            member_node_ids=sorted(combined),
                            naming_basis=naming,
                            edge_density=density,
                        )
                        used.add(j)
                        changed = True
                result.append(current)

            merged = result

        return merged

    def extract_features(self) -> list[Feature]:
        """Full extraction pipeline: nouns → cluster → merge → density."""
        noun_map = self.build_noun_to_nodes()
        candidates = self.cluster_by_shared_nouns(noun_map)
        merged = self.merge_overlapping(candidates)
        # Sort by edge density descending, then by member count
        return sorted(
            merged,
            key=lambda f: (f.edge_density, len(f.member_node_ids)),
            reverse=True,
        )

    # ── Helpers ──────────────────────────────────────────────────

    def _compute_edge_density(self, node_ids: list[str]) -> int:
        """Count edges between member nodes."""
        node_set = set(node_ids)
        count = 0
        for edge in self._edges:
            if edge.source in node_set and edge.target in node_set:
                count += 1
        return count

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        """Compute Jaccard similarity between two sets."""
        if not a or not b:
            return 0.0
        intersection = len(a & b)
        union = len(a | b)
        return intersection / union if union > 0 else 0.0
