"""Tests for runtime telemetry ingestion and storage."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from kb_agent.graph.telemetry import TelemetryIngestor, TelemetryStorage
from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.models.telemetry import FeedbackRecord, RuntimeMetadata, TraceSpan, TuningConfig


def _node(name: str, path: str = "svc.py", line: int = 1) -> SymbolNode:
    return SymbolNode(
        id=f"repo/{path}::{name}",
        name=name,
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        path=path,
        line_start=line,
        line_end=line + 5,
    )


def _edge(src: str, tgt: str, kind: EdgeKind = EdgeKind.CALLS) -> SymbolEdge:
    return SymbolEdge(source=src, target=tgt, kind=kind)


def _span(
    op_name: str,
    span_id: str = "span1",
    status: str = "OK",
    start: str = "2026-01-01T00:00:00",
    end: str = "2026-01-01T00:00:00.100",
    attrs: dict | None = None,
) -> TraceSpan:
    return TraceSpan(
        trace_id="trace1",
        span_id=span_id,
        operation_name=op_name,
        start_time=start,
        end_time=end,
        status_code=status,
        attributes=attrs or {},
    )


class TestTelemetryIngestor:
    def test_map_span_by_operation_name(self):
        nodes = [_node("handle_request"), _node("process_data")]
        ingestor = TelemetryIngestor(nodes, [])
        spans = [_span("handle_request")]
        mapped = ingestor.ingest_traces(spans)
        assert mapped[0].mapped_node_id == "repo/svc.py::handle_request"
        assert mapped[0].mapping_confidence == 0.90

    def test_map_span_by_filepath(self):
        nodes = [_node("main", path="app/server.py")]
        ingestor = TelemetryIngestor(nodes, [])
        spans = [_span("unknown_op", attrs={"code.filepath": "app/server.py"})]
        mapped = ingestor.ingest_traces(spans)
        assert mapped[0].mapped_node_id is not None
        assert mapped[0].mapping_confidence == 0.75

    def test_map_span_by_function_attribute(self):
        nodes = [_node("process_order")]
        ingestor = TelemetryIngestor(nodes, [])
        spans = [_span("unknown_op", attrs={"code.function": "process_order"})]
        mapped = ingestor.ingest_traces(spans)
        assert mapped[0].mapped_node_id == "repo/svc.py::process_order"
        assert mapped[0].mapping_confidence == 0.80

    def test_no_match_gets_zero_confidence(self):
        nodes = [_node("handle_request")]
        ingestor = TelemetryIngestor(nodes, [])
        spans = [_span("totally_different")]
        mapped = ingestor.ingest_traces(spans)
        assert mapped[0].mapped_node_id is None
        assert mapped[0].mapping_confidence == 0.0

    def test_compute_runtime_metadata_aggregation(self):
        nodes = [_node("handle_request")]
        ingestor = TelemetryIngestor(nodes, [])
        spans = [
            _span("handle_request", span_id="s1", start="2026-01-01T00:00:00", end="2026-01-01T00:00:00.100"),
            _span("handle_request", span_id="s2", start="2026-01-01T00:00:01", end="2026-01-01T00:00:01.050"),
        ]
        mapped = ingestor.ingest_traces(spans)
        meta = ingestor.compute_runtime_metadata(mapped)
        assert len(meta) == 1
        node_id = "repo/svc.py::handle_request"
        assert meta[node_id].call_count == 2
        assert meta[node_id].error_count == 0

    def test_latency_percentiles(self):
        nodes = [_node("svc")]
        ingestor = TelemetryIngestor(nodes, [])
        spans = [
            _span("svc", span_id=f"s{i}", start="2026-01-01T00:00:00", end=f"2026-01-01T00:00:00.{i * 10:03d}")
            for i in range(1, 11)
        ]
        mapped = ingestor.ingest_traces(spans)
        meta = ingestor.compute_runtime_metadata(mapped)
        m = meta["repo/svc.py::svc"]
        assert m.p50_latency_ms > 0
        assert m.p95_latency_ms >= m.p50_latency_ms

    def test_error_rate_computation(self):
        nodes = [_node("svc")]
        ingestor = TelemetryIngestor(nodes, [])
        spans = [
            _span("svc", span_id="s1", status="OK"),
            _span("svc", span_id="s2", status="ERROR"),
        ]
        mapped = ingestor.ingest_traces(spans)
        meta = ingestor.compute_runtime_metadata(mapped)
        assert meta["repo/svc.py::svc"].error_rate == 0.5
        assert meta["repo/svc.py::svc"].error_count == 1

    def test_update_graph_metadata_weights(self):
        nodes = [_node("a"), _node("b")]
        meta = {
            "repo/svc.py::a": RuntimeMetadata(node_id="repo/svc.py::a", call_count=10, error_rate=0.0),
            "repo/svc.py::b": RuntimeMetadata(node_id="repo/svc.py::b", call_count=5, error_rate=0.2),
        }
        ingestor = TelemetryIngestor(nodes, [])
        weights = ingestor.update_graph_metadata(meta)
        assert weights["repo/svc.py::a"] == 1.0
        assert weights["repo/svc.py::b"] == pytest.approx(0.4, abs=0.01)

    def test_runtime_weight_zero_for_no_calls(self):
        nodes = [_node("a")]
        meta = {"repo/svc.py::a": RuntimeMetadata(node_id="repo/svc.py::a", call_count=0)}
        ingestor = TelemetryIngestor(nodes, [])
        weights = ingestor.update_graph_metadata(meta)
        assert weights["repo/svc.py::a"] == 0.0


class TestTelemetryStorage:
    def test_persist_roundtrip_traces(self, tmp_path: Path):
        storage = TelemetryStorage(tmp_path / "telemetry")
        spans = [_span("test_op", span_id="s1")]
        storage.save_traces(spans, append=False)
        loaded = storage.load_traces()
        assert len(loaded) == 1
        assert loaded[0].operation_name == "test_op"

    def test_persist_roundtrip_runtime_metadata(self, tmp_path: Path):
        storage = TelemetryStorage(tmp_path / "telemetry")
        meta = {
            "node1": RuntimeMetadata(node_id="node1", call_count=100, p95_latency_ms=50.0),
        }
        storage.save_runtime_metadata(meta)
        loaded = storage.load_runtime_metadata()
        assert "node1" in loaded
        assert loaded["node1"].call_count == 100

    def test_persist_roundtrip_feedback(self, tmp_path: Path):
        storage = TelemetryStorage(tmp_path / "telemetry")
        records = [FeedbackRecord(query="test", response_node_ids=["n1"], useful=True)]
        storage.save_feedback(records, append=False)
        loaded = storage.load_feedback()
        assert len(loaded) == 1
        assert loaded[0].useful is True

    def test_append_traces(self, tmp_path: Path):
        storage = TelemetryStorage(tmp_path / "telemetry")
        storage.save_traces([_span("op1", span_id="s1")], append=False)
        storage.save_traces([_span("op2", span_id="s2")], append=True)
        loaded = storage.load_traces()
        assert len(loaded) == 2

    def test_load_empty_telemetry_dir(self, tmp_path: Path):
        storage = TelemetryStorage(tmp_path / "telemetry")
        assert storage.load_traces() == []
        assert storage.load_runtime_metadata() == {}
        assert storage.load_feedback() == []

    def test_tuning_config_roundtrip(self, tmp_path: Path):
        storage = TelemetryStorage(tmp_path / "telemetry")
        config = TuningConfig(
            hop_limit_adjustments={"default": 3},
            confidence_threshold_adjustments={"symbol_lookup": 0.65},
            sample_count=50,
            accuracy=0.85,
        )
        storage.save_tuning_config(config)
        loaded = storage.load_tuning_config()
        assert loaded is not None
        assert loaded.hop_limit_adjustments["default"] == 3
        assert loaded.accuracy == 0.85
