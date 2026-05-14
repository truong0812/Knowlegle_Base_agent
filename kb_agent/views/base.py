from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

from kb_agent.analyzer.llm import LLMClient
from kb_agent.models.entry import AIData, KBEntry, Language, StaticData, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode

UTILITY_PATTERNS = re.compile(
    r"(?:^|[_\.])(?:log(?:ger|ging)?|config|settings?|conf|util(?:s)?|helper"
    r"|metrics?|serialize|deserialize|cache|constants?|types?)(?:$|[_\.])",
    re.IGNORECASE,
)


class ViewIDMapper:
    """Shared lookup indexes and ID mapping for all view builders."""

    def __init__(self, nodes: list[SymbolNode], edges: list[SymbolEdge]) -> None:
        self._nodes = nodes
        self._edges = edges
        self.node_by_id: dict[str, SymbolNode] = {n.id: n for n in nodes}
        self.nodes_by_path: dict[str, list[str]] = {}
        self.edges_by_source: dict[str, list[SymbolEdge]] = {}
        self.edges_by_target: dict[str, list[SymbolEdge]] = {}

        for n in nodes:
            self.nodes_by_path.setdefault(n.path, []).append(n.id)

        for e in edges:
            self.edges_by_source.setdefault(e.source, []).append(e)
            self.edges_by_target.setdefault(e.target, []).append(e)

    def group_nodes_by_depth(self, depth: int) -> dict[str, list[str]]:
        """Group node IDs by configurable path depth.

        depth=1: "src/" -> ["n1", "n2"]
        depth=2: "src/services/" -> ["n1", "n2"]
        """
        groups: dict[str, list[str]] = {}
        for n in self._nodes:
            parts = Path(n.path).parts
            key = "/".join(parts[:depth]) if len(parts) >= depth else parts[0] if parts else "."
            groups.setdefault(key, []).append(n.id)
        return groups

    @staticmethod
    def is_utility_name(name: str) -> bool:
        return bool(UTILITY_PATTERNS.search(name))

    @staticmethod
    def sanitize_path(path: str) -> str:
        return path.replace("/", "_").replace("\\", "_").replace(".", "_")

    def find_module_for_file(self, file_path: str, depth: int) -> str:
        parts = Path(file_path).parts
        return "/".join(parts[:depth]) if len(parts) >= depth else (parts[0] if parts else ".")


class ViewBuilder(ABC):
    """Base class for materialized view builders."""

    def __init__(self, mapper: ViewIDMapper, llm: LLMClient | None = None) -> None:
        self._mapper = mapper
        self._llm = llm

    @abstractmethod
    async def build(self, **kwargs) -> list[KBEntry]: ...

    @staticmethod
    def _make_static(node: SymbolNode, **overrides) -> StaticData:
        defaults = dict(
            kind=node.kind,
            language=node.language,
            path=node.path,
            line_start=node.line_start,
            line_end=node.line_end,
            signature=node.signature,
            modifiers=node.modifiers,
            parameters=node.parameters,
            return_type=node.return_type,
            docstring=node.docstring,
        )
        defaults.update(overrides)
        return StaticData(**defaults)
