"""Temporal graph manager — versioned snapshots at commit boundaries."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from kb_agent.graph.storage import GraphStorage
from kb_agent.models.graph import SymbolEdge, SymbolNode
from kb_agent.models.temporal import EdgeDiff, GraphVersion, NodeDiff, VersionDiff

logger = logging.getLogger(__name__)


class TemporalGraphManager:
    """Manages versioned graph snapshots."""

    def __init__(self, graph_dir: Path) -> None:
        self._versions_dir = graph_dir / "versions"

    def save_snapshot(
        self,
        version_id: str,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
        commit_hash: str | None = None,
        parent_version: str | None = None,
    ) -> GraphVersion:
        """Save a versioned snapshot of the graph."""
        version_dir = self._versions_dir / version_id
        version_dir.mkdir(parents=True, exist_ok=True)

        # Write nodes and edges using GraphStorage into version dir
        storage = GraphStorage(version_dir)
        storage.save(nodes, edges)

        version = GraphVersion(
            version_id=version_id,
            commit_hash=commit_hash,
            timestamp=datetime.now().isoformat(),
            node_count=len(nodes),
            edge_count=len(edges),
            parent_version=parent_version,
        )

        meta_path = version_dir / "version_meta.json"
        meta_path.write_text(version.model_dump_json(indent=2), encoding="utf-8")
        return version

    def load_snapshot(
        self, version_id: str,
    ) -> tuple[list[SymbolNode], list[SymbolEdge]]:
        """Load a specific version snapshot."""
        version_dir = self._versions_dir / version_id
        storage = GraphStorage(version_dir)
        return storage.load()

    def list_versions(self) -> list[GraphVersion]:
        """List all stored versions sorted by timestamp ascending."""
        if not self._versions_dir.exists():
            return []
        versions: list[GraphVersion] = []
        for child in self._versions_dir.iterdir():
            if not child.is_dir():
                continue
            meta_path = child / "version_meta.json"
            if not meta_path.exists():
                continue
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                versions.append(GraphVersion(**data))
            except (json.JSONDecodeError, Exception):
                continue
        return sorted(versions, key=lambda v: v.timestamp)

    def latest_version(self) -> GraphVersion | None:
        """Return the most recent version, or None if no versions exist."""
        versions = self.list_versions()
        return versions[-1] if versions else None

    def diff_versions(self, from_id: str, to_id: str) -> VersionDiff:
        """Compute diff between two versions."""
        from_nodes, from_edges = self.load_snapshot(from_id)
        to_nodes, to_edges = self.load_snapshot(to_id)

        from_node_ids = {n.id for n in from_nodes}
        to_node_ids = {n.id for n in to_nodes}

        # Detect modified nodes (same ID but different signature/line range)
        from_node_map = {n.id: n for n in from_nodes}
        to_node_map = {n.id: n for n in to_nodes}

        added_nodes = sorted(to_node_ids - from_node_ids)
        removed_nodes = sorted(from_node_ids - to_node_ids)
        modified_nodes: list[str] = []
        for nid in from_node_ids & to_node_ids:
            fn = from_node_map[nid]
            tn = to_node_map[nid]
            if fn.signature != tn.signature or fn.line_start != tn.line_start or fn.line_end != tn.line_end:
                modified_nodes.append(nid)

        # Edge diff by (source, target, kind) tuples
        from_edge_set = {(e.source, e.target, e.kind.value) for e in from_edges}
        to_edge_set = {(e.source, e.target, e.kind.value) for e in to_edges}

        added_edges = sorted(f"{s}--{k}-->{t}" for s, t, k in (to_edge_set - from_edge_set))
        removed_edges = sorted(f"{s}--{k}-->{t}" for s, t, k in (from_edge_set - to_edge_set))

        return VersionDiff(
            from_version=from_id,
            to_version=to_id,
            node_diff=NodeDiff(added=added_nodes, removed=removed_nodes, modified=sorted(modified_nodes)),
            edge_diff=EdgeDiff(added=added_edges, removed=removed_edges),
        )
