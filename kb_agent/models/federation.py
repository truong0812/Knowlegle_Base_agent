"""Federation models for multi-repository graph references."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field


class RepositoryRef(BaseModel):
    """Reference to a registered external repository."""
    repo_id: str
    repo_path: str
    repo_name: str
    registered_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    node_count: int = 0
    edge_count: int = 0


class CrossRepoReference(BaseModel):
    """A cross-repository symbol reference."""
    source_repo: str
    source_node_id: str
    target_repo: str
    target_node_id: str
    reference_kind: str = "import"
    confidence: float = 1.0


@dataclass
class FederationResult:
    """Result of cross-repo symbol resolution: edges + foreign nodes to import."""
    edges: list = field(default_factory=list)          # list[SymbolEdge]
    foreign_nodes: list = field(default_factory=list)   # list[SymbolNode]
