"""Temporal query handler — answer version-diff queries."""
from __future__ import annotations

from kb_agent.graph.temporal import TemporalGraphManager
from kb_agent.models.graph import SymbolEdge, SymbolNode
from kb_agent.models.temporal import VersionDiff


class TemporalQueryHandler:
    """Handles temporal/version-diff queries against the graph."""

    def __init__(self, graph_dir) -> None:
        from pathlib import Path
        self._manager = TemporalGraphManager(Path(graph_dir))

    def what_changed_since(
        self,
        version_id: str,
        current_nodes: list[SymbolNode],
        current_edges: list[SymbolEdge],
    ) -> VersionDiff:
        """Diff a stored version against the current in-memory graph state."""
        return self._manager.diff_against(version_id, current_nodes, current_edges)

    def diff_versions(self, from_id: str, to_id: str) -> VersionDiff:
        """Diff two stored versions."""
        return self._manager.diff_versions(from_id, to_id)

    @staticmethod
    def format_diff(diff: VersionDiff) -> str:
        """Produce human-readable diff output."""
        lines: list[str] = []
        lines.append(f"Changes from {diff.from_version} to {diff.to_version}:")

        nd = diff.node_diff
        lines.append(f"  Nodes added:    {len(nd.added)}")
        lines.append(f"  Nodes removed:  {len(nd.removed)}")
        lines.append(f"  Nodes modified: {len(nd.modified)}")

        if nd.added:
            lines.append("  Added:")
            for nid in nd.added[:10]:
                lines.append(f"    + {nid}")

        if nd.removed:
            lines.append("  Removed:")
            for nid in nd.removed[:10]:
                lines.append(f"    - {nid}")

        if nd.modified:
            lines.append("  Modified:")
            for nid in nd.modified[:10]:
                lines.append(f"    ~ {nid}")

        ed = diff.edge_diff
        lines.append(f"  Edges added:    {len(ed.added)}")
        lines.append(f"  Edges removed:  {len(ed.removed)}")

        if ed.added:
            lines.append("  Added edges:")
            for e in ed.added[:10]:
                lines.append(f"    + {e}")

        if ed.removed:
            lines.append("  Removed edges:")
            for e in ed.removed[:10]:
                lines.append(f"    - {e}")

        return "\n".join(lines)
