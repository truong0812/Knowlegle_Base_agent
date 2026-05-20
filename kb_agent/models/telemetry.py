"""Telemetry models for runtime trace ingestion and feedback."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TraceSpan(BaseModel):
    """A single OpenTelemetry span mapped to a graph node."""
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    operation_name: str
    start_time: str  # ISO 8601
    end_time: str    # ISO 8601
    status_code: str = "OK"
    attributes: dict[str, str] = Field(default_factory=dict)
    mapped_node_id: str | None = None
    mapping_confidence: float = 0.0


class RuntimeMetadata(BaseModel):
    """Aggregated runtime stats for a single symbol node."""
    node_id: str
    call_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    last_seen: str | None = None
    error_rate: float = 0.0


class FeedbackRecord(BaseModel):
    """A single query-response feedback pair."""
    query: str
    response_node_ids: list[str]
    useful: bool
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, str] = Field(default_factory=dict)


class TuningConfig(BaseModel):
    """Learned retrieval tuning parameters."""
    edge_weight_adjustments: dict[str, float] = Field(default_factory=dict)
    hop_limit_adjustments: dict[str, int] = Field(default_factory=dict)
    confidence_threshold_adjustments: dict[str, float] = Field(default_factory=dict)
    suppression_rules: list[str] = Field(default_factory=list)
    trained_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    sample_count: int = 0
    accuracy: float = 0.0
