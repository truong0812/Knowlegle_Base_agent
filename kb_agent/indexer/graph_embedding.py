"""Graph-aware embedding text enrichment.

Enriches the text fed to sentence-transformers with structural graph context
(calls, callers, features, hotness) to improve semantic seed quality.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from kb_agent.graph.features import Feature
from kb_agent.graph.hotpath import HotPathScore
from kb_agent.graph.storage import GraphStorage
from kb_agent.models.entry import KBEntry, Layer
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode

logger = logging.getLogger(__name__)


class GraphAwareEmbedder:
    """Builds enriched embedding texts using graph context."""

    def __init__(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
        features: list[Feature] | None = None,
        hotpath: dict[str, HotPathScore] | None = None,
    ) -> None:
        self._node_index: dict[str, SymbolNode] = {n.id: n for n in nodes}
        self._edges_by_source: dict[str, list[SymbolEdge]] = {}
        self._edges_by_target: dict[str, list[SymbolEdge]] = {}
        self._features = features or []
        self._hotpath = hotpath or {}

        for e in edges:
            self._edges_by_source.setdefault(e.source, []).append(e)
            self._edges_by_target.setdefault(e.target, []).append(e)

        # Build node_id -> feature_names reverse index
        self._node_features: dict[str, list[str]] = {}
        for feat in self._features:
            for nid in feat.member_node_ids:
                self._node_features.setdefault(nid, []).append(feat.name)

        # Build path+line -> node_id index for entry mapping
        self._path_line_to_node: dict[tuple[str, int], str] = {}
        for n in nodes:
            self._path_line_to_node[(n.path, n.line_start)] = n.id

    @classmethod
    def from_graph_dir(cls, graph_dir: Path) -> GraphAwareEmbedder | None:
        """Construct from a graph directory. Returns None if graph data missing."""
        if not graph_dir.exists():
            return None
        storage = GraphStorage(graph_dir)
        try:
            nodes, edges = storage.load()
        except (FileNotFoundError, json.JSONDecodeError):
            return None

        features = storage.load_features()
        hotpath = storage.load_hotpath()
        return cls(nodes, edges, features, hotpath)

    def enrich_text(self, entry: KBEntry) -> str:
        """Build enriched embedding text for a KB entry.

        MEM entries get graph context; other layers keep plain text.
        """
        base = f"{entry.id}: {entry.ai.summary or entry.static.signature or entry.static.kind.value}"

        if entry.layer != Layer.MEM:
            return base

        node_id = self._path_line_to_node.get(
            (entry.static.path, entry.static.line_start),
        )
        if not node_id:
            return base

        parts: list[str] = [base]

        # Calls made by this node
        calls = self._edges_by_source.get(node_id, [])
        call_targets = [
            self._node_name(e.target) for e in calls if e.kind == EdgeKind.CALLS
        ]
        if call_targets:
            parts.append(f"calls: {', '.join(call_targets[:10])}")

        # Callers of this node
        callers = self._edges_by_target.get(node_id, [])
        caller_names = [
            self._node_name(e.source) for e in callers if e.kind == EdgeKind.CALLS
        ]
        if caller_names:
            parts.append(f"called by: {', '.join(caller_names[:10])}")

        # Feature membership
        feat_names = self._node_features.get(node_id, [])
        if feat_names:
            parts.append(f"features: {', '.join(feat_names[:5])}")

        # Hot-path score
        hp = self._hotpath.get(node_id)
        if hp and hp.hotness > 0:
            parts.append(f"hotness: {hp.hotness:.2f}")

        return " | ".join(parts)

    def _node_name(self, node_id: str) -> str:
        node = self._node_index.get(node_id)
        if node:
            return node.name
        # Fallback: extract name from ID
        if "::" in node_id:
            return node_id.split("::")[-1].split("(")[0]
        return node_id
