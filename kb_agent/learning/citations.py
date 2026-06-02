"""Citation helpers for learning platform placeholders."""
from __future__ import annotations

from kb_agent.learning.models import Citation
from kb_agent.models.graph import SymbolNode


def citation_from_node(node: SymbolNode) -> Citation:
    """Build a source citation from a graph node."""

    return Citation(
        label=f"{node.name} ({node.path}:{node.line_start})",
        path=node.path,
        line_start=node.line_start,
        line_end=node.line_end,
        node_id=node.id,
    )

