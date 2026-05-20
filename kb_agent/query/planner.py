"""Query planner — routes different intents to different expansion strategies."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kb_agent.models.graph import EdgeKind
from kb_agent.models.telemetry import TuningConfig
from kb_agent.query.intent import QueryIntent


@dataclass(frozen=True)
class ExpansionStrategy:
    max_hops: int
    max_nodes: int
    max_edges_per_node: int
    min_confidence: float
    follow_edge_kinds: tuple[EdgeKind, ...]
    direction: str  # "outgoing" | "incoming" | "bidirectional"


STRATEGY_TABLE: dict[QueryIntent, ExpansionStrategy] = {
    QueryIntent.SYMBOL_LOOKUP: ExpansionStrategy(
        max_hops=1,
        max_nodes=8,
        max_edges_per_node=3,
        min_confidence=0.70,
        follow_edge_kinds=(EdgeKind.CALLS, EdgeKind.USES_TYPE, EdgeKind.CONTAINS),
        direction="outgoing",
    ),
    QueryIntent.FLOW_TRACE: ExpansionStrategy(
        max_hops=3,
        max_nodes=15,
        max_edges_per_node=5,
        min_confidence=0.60,
        follow_edge_kinds=(EdgeKind.CALLS,),
        direction="outgoing",
    ),
    QueryIntent.MODULE_OVERVIEW: ExpansionStrategy(
        max_hops=1,
        max_nodes=20,
        max_edges_per_node=3,
        min_confidence=0.50,
        follow_edge_kinds=(EdgeKind.CONTAINS, EdgeKind.IMPORTS),
        direction="bidirectional",
    ),
    QueryIntent.RELATIONSHIP: ExpansionStrategy(
        max_hops=2,
        max_nodes=10,
        max_edges_per_node=5,
        min_confidence=0.60,
        follow_edge_kinds=(EdgeKind.CALLS, EdgeKind.USES_TYPE, EdgeKind.IMPORTS),
        direction="incoming",
    ),
    QueryIntent.VERSION_DIFF: ExpansionStrategy(
        max_hops=1,
        max_nodes=10,
        max_edges_per_node=3,
        min_confidence=0.60,
        follow_edge_kinds=(EdgeKind.CALLS, EdgeKind.CONTAINS),
        direction="bidirectional",
    ),
    QueryIntent.CHAIN_TRACE: ExpansionStrategy(
        max_hops=4,
        max_nodes=25,
        max_edges_per_node=8,
        min_confidence=0.50,
        follow_edge_kinds=(EdgeKind.CALLS, EdgeKind.IMPLEMENTS),
        direction="outgoing",
    ),
    QueryIntent.DEFAULT: ExpansionStrategy(
        max_hops=2,
        max_nodes=15,
        max_edges_per_node=5,
        min_confidence=0.60,
        follow_edge_kinds=tuple(EdgeKind),
        direction="bidirectional",
    ),
}


class QueryPlanner:
    """Selects expansion strategy based on query intent."""

    def __init__(self, tuning_config: TuningConfig | None = None) -> None:
        self._overrides = tuning_config

    def plan(self, intent: QueryIntent) -> ExpansionStrategy:
        base = STRATEGY_TABLE.get(intent, STRATEGY_TABLE[QueryIntent.DEFAULT])
        if self._overrides is None:
            return base
        return self._apply_overrides(base, intent)

    def _apply_overrides(self, base: ExpansionStrategy, intent: QueryIntent) -> ExpansionStrategy:
        overrides = self._overrides
        if overrides is None:
            return base

        max_hops = base.max_hops
        min_confidence = base.min_confidence

        intent_key = intent.value
        if intent_key in overrides.hop_limit_adjustments:
            max_hops = overrides.hop_limit_adjustments[intent_key]
        if intent_key in overrides.confidence_threshold_adjustments:
            min_confidence = overrides.confidence_threshold_adjustments[intent_key]

        return ExpansionStrategy(
            max_hops=max_hops,
            max_nodes=base.max_nodes,
            max_edges_per_node=base.max_edges_per_node,
            min_confidence=min_confidence,
            follow_edge_kinds=base.follow_edge_kinds,
            direction=base.direction,
        )

    @classmethod
    def from_telemetry(cls, kb_dir: Path) -> QueryPlanner:
        """Load tuning config from .kb/telemetry/ if available."""
        from kb_agent.graph.telemetry import TelemetryStorage

        tel_dir = kb_dir / "telemetry"
        if not tel_dir.exists():
            return cls()
        storage = TelemetryStorage(tel_dir)
        config = storage.load_tuning_config()
        return cls(tuning_config=config)
