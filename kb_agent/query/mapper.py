"""Map FAISS seed entries to graph SymbolNodes."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from kb_agent.graph.storage import GraphStorage
from kb_agent.models.entry import KBEntry
from kb_agent.models.graph import SymbolNode


@dataclass
class MappingResult:
    seed_nodes: list[SymbolNode]
    unmapped_entries: list[KBEntry]
    path_line_index: dict[tuple[str, int], SymbolNode] = field(repr=False)


def build_entry_to_node_mapper(
    entries: list[KBEntry],
    graph_dir: Path,
) -> MappingResult | None:
    """Build (path, line_start) -> SymbolNode index and map MEM entries.

    Returns None when no graph directory exists (legacy KB without --with-graph).
    """
    if not graph_dir.exists():
        return None

    nodes, _ = GraphStorage(graph_dir).load()
    if not nodes:
        return None

    path_line_index: dict[tuple[str, int], SymbolNode] = {}
    for node in nodes:
        key = (node.path, node.line_start)
        if key not in path_line_index or (
            node.line_end - node.line_start
            < path_line_index[key].line_end - path_line_index[key].line_start
        ):
            path_line_index[key] = node

    seed_nodes: list[SymbolNode] = []
    unmapped: list[KBEntry] = []
    seen: set[str] = set()

    for entry in entries:
        if entry.layer.value != "mem":
            unmapped.append(entry)
            continue
        node = path_line_index.get((entry.static.path, entry.static.line_start))
        if node and node.id not in seen:
            seed_nodes.append(node)
            seen.add(node.id)
        else:
            unmapped.append(entry)

    return MappingResult(
        seed_nodes=seed_nodes,
        unmapped_entries=unmapped,
        path_line_index=path_line_index,
    )
