from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Layer(str, Enum):
    ARCH = "arch"
    MOD = "mod"
    MEM = "mem"


class SymbolKind(str, Enum):
    PACKAGE = "package"
    MODULE = "module"
    CLASS = "class"
    STRUCT = "struct"
    INTERFACE = "interface"
    METHOD = "method"
    FUNCTION = "function"
    PROPERTY = "property"
    ENUM = "enum"


class Language(str, Enum):
    PYTHON = "python"
    CSHARP = "csharp"
    CPP = "cpp"


class Parameter(BaseModel):
    name: str
    type: str | None = None
    default_value: str | None = None


class StaticData(BaseModel):
    model_config = {"extra": "allow"}

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
    imports: list[str] = Field(default_factory=list)
    source: str = "ast"
    files: list[str] | None = None
    exports: list[str] | None = None


class AIData(BaseModel):
    summary: str | None = None
    purpose: str | None = None
    behavior: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "llm"


class KBEntry(BaseModel):
    id: str
    layer: Layer
    parent: str | None = None
    children: list[str] = Field(default_factory=list)
    static: StaticData
    ai: AIData = Field(default_factory=AIData)
