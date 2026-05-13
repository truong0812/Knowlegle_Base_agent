from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from kb_agent.models.entry import Language, Parameter, SymbolKind


@dataclass
class SymbolInfo:
    """Raw symbol extracted by parser, before becoming a KBEntry."""

    name: str
    kind: SymbolKind
    line_start: int
    line_end: int
    signature: str | None = None
    modifiers: list[str] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    return_type: str | None = None
    docstring: str | None = None
    children: list[SymbolInfo] = field(default_factory=list)


@dataclass
class ImportInfo:
    module_path: str
    imported_names: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    """Output of parsing a single source file."""

    file_path: str
    language: Language
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class BaseParser(ABC):
    """Abstract parser. Each language implements this."""

    @abstractmethod
    def parse_file(self, source: bytes, file_path: str) -> ParseResult: ...

    @abstractmethod
    def extract_symbols(self, root_node) -> list[SymbolInfo]: ...

    @abstractmethod
    def extract_imports(self, root_node) -> list[ImportInfo]: ...

    def _node_text(self, node) -> str:
        return node.text.decode("utf-8")
