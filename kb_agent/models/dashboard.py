"""Dashboard models for observability metrics."""
from __future__ import annotations

from pydantic import BaseModel, Field


class GraphHealthMetrics(BaseModel):
    """Health metrics for the symbol graph."""
    total_nodes: int = 0
    total_edges: int = 0
    edge_density: float = 0.0
    avg_confidence: float = 0.0
    confidence_distribution: dict[str, int] = Field(default_factory=dict)
    orphan_nodes: int = 0
    orphan_ratio: float = 0.0
    edge_kind_distribution: dict[str, int] = Field(default_factory=dict)
    bridge_count: int = 0
    cross_repo_edge_count: int = 0


class RetrievalAnalytics(BaseModel):
    """Query performance and relevance metrics."""
    total_queries: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_seed_nodes: float = 0.0
    avg_expanded_nodes: float = 0.0
    avg_expansion_ratio: float = 0.0
    truncation_rate: float = 0.0
    intent_distribution: dict[str, int] = Field(default_factory=dict)
    feedback_useful_rate: float = 0.0
    feedback_total: int = 0


class DebugInfo(BaseModel):
    """Debug trace for a single retrieval query."""
    query: str
    intent: str
    seed_nodes: list[str] = Field(default_factory=list)
    expansion_path: list[str] = Field(default_factory=list)
    suppression_log: list[str] = Field(default_factory=list)
    edge_follow_log: list[str] = Field(default_factory=list)
    token_budget_breakdown: dict[str, int] = Field(default_factory=dict)
