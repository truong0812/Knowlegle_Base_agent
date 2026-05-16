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
    bases: list[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    module_path: str
    imported_names: list[str] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)


@dataclass
class CallInfo:
    """A call expression found in a function/method body."""

    caller_name: str
    callee_name: str
    line: int
    resolution_method: str  # "same_scope", "same_file", "direct_import", "constructor", "static_call", "dynamic_dispatch", "unresolved"
    is_self_call: bool = False
    receiver: str | None = None


@dataclass
class TypeUsageInfo:
    """A type reference found in a parameter, return type, or annotation."""

    symbol_name: str
    type_name: str
    usage_context: str  # "parameter", "return_type", "annotation"
    line: int


@dataclass
class ParseResult:
    """Output of parsing a single source file."""

    file_path: str
    language: Language
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    calls: list[CallInfo] = field(default_factory=list)
    type_usages: list[TypeUsageInfo] = field(default_factory=list)
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
