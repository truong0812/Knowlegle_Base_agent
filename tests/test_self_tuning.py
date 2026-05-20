"""Tests for self-tuning retrieval system."""
from __future__ import annotations

from pathlib import Path

import pytest

from kb_agent.graph.telemetry import TelemetryStorage
from kb_agent.models.telemetry import FeedbackRecord, TuningConfig
from kb_agent.query.self_tuning import SelfTuningRetrieval


def _make_feedback(n: int, useful: bool, storage: TelemetryStorage) -> None:
    """Create n feedback records and save them."""
    records = [
        FeedbackRecord(
            query=f"query_{i}",
            response_node_ids=[f"node_{i}"],
            useful=useful,
        )
        for i in range(n)
    ]
    storage.save_feedback(records, append=False)


class TestSelfTuningRetrieval:
    def test_collect_feedback(self, tmp_path: Path):
        storage = TelemetryStorage(tmp_path / "telemetry")
        tuner = SelfTuningRetrieval(storage)
        record = tuner.collect_feedback("test query", ["node1", "node2"], useful=True)
        assert record.query == "test query"
        assert record.useful is True
        loaded = storage.load_feedback()
        assert len(loaded) == 1

    def test_train_ranking_insufficient_data(self, tmp_path: Path):
        storage = TelemetryStorage(tmp_path / "telemetry")
        _make_feedback(5, True, storage)
        tuner = SelfTuningRetrieval(storage)
        result = tuner.train_ranking_model(min_samples=20)
        assert result is None

    def test_train_ranking_low_relevance(self, tmp_path: Path):
        storage = TelemetryStorage(tmp_path / "telemetry")
        _make_feedback(25, False, storage)
        tuner = SelfTuningRetrieval(storage)
        config = tuner.train_ranking_model(min_samples=20)
        assert config is not None
        assert config.sample_count == 25
        assert config.accuracy < 0.5
        assert "symbol_lookup" in config.hop_limit_adjustments

    def test_train_ranking_high_relevance(self, tmp_path: Path):
        storage = TelemetryStorage(tmp_path / "telemetry")
        _make_feedback(25, True, storage)
        tuner = SelfTuningRetrieval(storage)
        config = tuner.train_ranking_model(min_samples=20)
        assert config is not None
        assert config.accuracy > 0.8

    def test_auto_tune_applies_overrides(self, tmp_path: Path):
        storage = TelemetryStorage(tmp_path / "telemetry")
        tuner = SelfTuningRetrieval(storage)
        config = TuningConfig(
            hop_limit_adjustments={"default": 3},
            confidence_threshold_adjustments={"default": 0.65},
            sample_count=50,
            accuracy=0.8,
        )
        tuner.auto_tune_parameters(config)
        loaded = storage.load_tuning_config()
        assert loaded is not None
        assert loaded.hop_limit_adjustments["default"] == 3

    def test_get_tuning_stats(self, tmp_path: Path):
        storage = TelemetryStorage(tmp_path / "telemetry")
        _make_feedback(10, True, storage)
        _make_feedback_with_useful_false(5, storage)
        tuner = SelfTuningRetrieval(storage)
        stats = tuner.get_tuning_stats()
        assert stats["feedback_total"] == 15
        assert stats["useful_rate"] == pytest.approx(10 / 15, abs=0.01)


def _make_feedback_with_useful_false(n: int, storage: TelemetryStorage) -> None:
    records = [
        FeedbackRecord(query=f"q_bad_{i}", response_node_ids=[f"n_{i}"], useful=False)
        for i in range(n)
    ]
    storage.save_feedback(records, append=True)


class TestTunedPlanner:
    def test_overrides_applied_to_strategy(self):
        from kb_agent.query.planner import QueryPlanner
        from kb_agent.query.intent import QueryIntent

        config = TuningConfig(
            hop_limit_adjustments={"symbol_lookup": 3},
            confidence_threshold_adjustments={"symbol_lookup": 0.50},
        )
        planner = QueryPlanner(tuning_config=config)
        strategy = planner.plan(QueryIntent.SYMBOL_LOOKUP)
        assert strategy.max_hops == 3
        assert strategy.min_confidence == 0.50

    def test_no_overrides_returns_base_strategy(self):
        from kb_agent.query.planner import QueryPlanner, STRATEGY_TABLE
        from kb_agent.query.intent import QueryIntent

        planner = QueryPlanner()
        strategy = planner.plan(QueryIntent.SYMBOL_LOOKUP)
        base = STRATEGY_TABLE[QueryIntent.SYMBOL_LOOKUP]
        assert strategy == base

    def test_from_telemetry_factory(self, tmp_path: Path):
        from kb_agent.query.planner import QueryPlanner

        tel_dir = tmp_path / "telemetry"
        tel_dir.mkdir()
        storage = TelemetryStorage(tel_dir)
        config = TuningConfig(hop_limit_adjustments={"default": 4})
        storage.save_tuning_config(config)

        planner = QueryPlanner.from_telemetry(tmp_path)
        from kb_agent.query.intent import QueryIntent
        strategy = planner.plan(QueryIntent.DEFAULT)
        assert strategy.max_hops == 4

    def test_from_telemetry_no_dir(self, tmp_path: Path):
        from kb_agent.query.planner import QueryPlanner

        planner = QueryPlanner.from_telemetry(tmp_path)
        from kb_agent.query.intent import QueryIntent
        strategy = planner.plan(QueryIntent.DEFAULT)
        assert strategy.max_hops == 2  # base value


class TestRetrievalEngineAutoLoad:
    def test_retrieval_engine_auto_loads_tuning_config(self, tmp_path: Path):
        """Verify RetrievalEngine auto-loads tuning config from .kb/telemetry/."""
        from kb_agent.query.retrieval import RetrievalEngine

        # Set up a minimal .kb/telemetry/tuning_config.json
        kb_dir = tmp_path / "kb"
        tel_dir = kb_dir / "telemetry"
        tel_dir.mkdir(parents=True)

        storage = TelemetryStorage(tel_dir)
        config = TuningConfig(
            hop_limit_adjustments={"default": 5},
            confidence_threshold_adjustments={"default": 0.30},
        )
        storage.save_tuning_config(config)

        # RetrievalEngine should auto-load the tuning config
        engine = RetrievalEngine(kb_dir)
        assert engine._tuning_config is not None
        assert engine._tuning_config.hop_limit_adjustments["default"] == 5

    def test_retrieval_engine_no_tuning_graceful(self, tmp_path: Path):
        """Without telemetry dir, tuning_config stays None."""
        from kb_agent.query.retrieval import RetrievalEngine

        kb_dir = tmp_path / "kb"
        engine = RetrievalEngine(kb_dir)
        assert engine._tuning_config is None
