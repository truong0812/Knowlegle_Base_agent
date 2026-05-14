from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from kb_agent.models.entry import Language, Parameter, SymbolKind


class EdgeKind(str, Enum):
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    CONTAINS = "contains"
    USES_TYPE = "uses_type"


class SymbolNode(BaseModel):
    id: str
    name: str
    kind: SymbolKind
    language: Language
    path: str
    line_start: int
    line_end: int
    signature: str | None = None
    modifiers: list[str] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)
    return_type: str | None = None
    docstring: str | None = None


class SymbolEdge(BaseModel):
    source: str
    target: str
    kind: EdgeKind
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_type: str = "deterministic"
    resolution: str = "direct"