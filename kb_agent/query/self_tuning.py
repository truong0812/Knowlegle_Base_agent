"""Self-tuning retrieval: collect feedback and auto-tune retrieval parameters."""
from __future__ import annotations

import logging
from pathlib import Path

from kb_agent.graph.telemetry import TelemetryStorage
from kb_agent.models.telemetry import FeedbackRecord, TuningConfig

logger = logging.getLogger(__name__)


class SelfTuningRetrieval:
    """Collect feedback and auto-tune retrieval parameters."""

    def __init__(
        self,
        telemetry_storage: TelemetryStorage,
        graph_dir: Path | None = None,
    ) -> None:
        self._storage = telemetry_storage
        self._graph_dir = graph_dir

    def collect_feedback(
        self,
        query: str,
        response_node_ids: list[str],
        useful: bool,
        metadata: dict[str, str] | None = None,
    ) -> FeedbackRecord:
        """Record feedback for a query-response pair."""
        record = FeedbackRecord(
            query=query,
            response_node_ids=response_node_ids,
            useful=useful,
            metadata=metadata or {},
        )
        self._storage.save_feedback([record], append=True)
        return record

    def train_ranking_model(self, min_samples: int = 20) -> TuningConfig | None:
        """Train a simple ranking model from feedback data.

        Uses heuristic adjustment when scikit-learn is not available.
        Returns None if insufficient data.
        """
        feedback = self._storage.load_feedback()
        if len(feedback) < min_samples:
            logger.info("Insufficient feedback: %d < %d", len(feedback), min_samples)
            return None

        useful = [f for f in feedback if f.useful]
        not_useful = [f for f in feedback if not f.useful]

        useful_rate = len(useful) / len(feedback) if feedback else 0.0

        # Heuristic: adjust hop limits and confidence based on useful rate
        hop_adjustments: dict[str, int] = {}
        confidence_adjustments: dict[str, float] = {}

        if useful_rate < 0.5:
            # Low relevance: increase hops and lower confidence threshold
            hop_adjustments = {
                "symbol_lookup": 2,
                "flow_trace": 4,
                "relationship": 3,
                "default": 3,
            }
            confidence_adjustments = {
                "symbol_lookup": 0.60,
                "flow_trace": 0.50,
                "default": 0.50,
            }
        elif useful_rate > 0.8:
            # High relevance: can be more selective
            hop_adjustments = {
                "default": 2,
            }
            confidence_adjustments = {
                "default": 0.70,
            }

        config = TuningConfig(
            hop_limit_adjustments=hop_adjustments,
            confidence_threshold_adjustments=confidence_adjustments,
            sample_count=len(feedback),
            accuracy=useful_rate,
        )
        return config

    def auto_tune_parameters(self, config: TuningConfig) -> None:
        """Apply learned parameters by saving tuning config."""
        self._storage.save_tuning_config(config)
        logger.info(
            "Auto-tuning applied: %d hop overrides, %d confidence overrides",
            len(config.hop_limit_adjustments),
            len(config.confidence_threshold_adjustments),
        )

    def get_tuning_stats(self) -> dict:
        """Return current tuning statistics."""
        feedback = self._storage.load_feedback()
        config = self._storage.load_tuning_config()

        useful = sum(1 for f in feedback if f.useful)
        total = len(feedback)

        return {
            "feedback_total": total,
            "useful_rate": useful / total if total > 0 else 0.0,
            "accuracy": config.accuracy if config else 0.0,
            "active_overrides": (
                {**config.hop_limit_adjustments, **config.confidence_threshold_adjustments}
                if config else {}
            ),
        }
