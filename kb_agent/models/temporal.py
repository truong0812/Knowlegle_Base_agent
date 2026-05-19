"""Temporal graph models for versioned snapshots."""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel


class GraphVersion(BaseModel):
    version_id: str
    commit_hash: str | None = None
    timestamp: str
    node_count: int
    edge_count: int
    parent_version: str | None = None


@dataclass
class NodeDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)


@dataclass
class EdgeDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


class VersionDiff(BaseModel):
    from_version: str
    to_version: str
    node_diff: NodeDiff = NodeDiff()
    edge_diff: EdgeDiff = EdgeDiff()
