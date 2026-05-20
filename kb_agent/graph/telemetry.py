"""Runtime telemetry: ingest OpenTelemetry traces and map to symbol graph nodes."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from kb_agent.models.graph import SymbolEdge, SymbolNode
from kb_agent.models.telemetry import FeedbackRecord, RuntimeMetadata, TraceSpan, TuningConfig

logger = logging.getLogger(__name__)

MAPPING_CONFIDENCE = {
    "exact_name": 0.90,
    "filepath_match": 0.75,
    "function_attribute": 0.80,
    "partial_name": 0.50,
}


class TelemetryStorage:
    """Storage for telemetry data: traces, runtime metadata, feedback, tuning."""

    def __init__(self, telemetry_dir: Path) -> None:
        self._dir = telemetry_dir

    def save_traces(self, spans: list[TraceSpan], append: bool = True) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / "traces.jsonl"
        mode = "a" if append and path.exists() else "w"
        with open(path, mode, encoding="utf-8") as f:
            for span in spans:
                f.write(span.model_dump_json() + "\n")

    def load_traces(self) -> list[TraceSpan]:
        path = self._dir / "traces.jsonl"
        if not path.exists():
            return []
        spans: list[TraceSpan] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                spans.append(TraceSpan(**json.loads(line)))
        return spans

    def save_runtime_metadata(self, metadata: dict[str, RuntimeMetadata]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / "runtime_metadata.json"
        data = {nid: m.model_dump() for nid, m in metadata.items()}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_runtime_metadata(self) -> dict[str, RuntimeMetadata]:
        path = self._dir / "runtime_metadata.json"
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return {nid: RuntimeMetadata(**m) for nid, m in data.items()}

    def save_feedback(self, records: list[FeedbackRecord], append: bool = True) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / "feedback.jsonl"
        mode = "a" if append and path.exists() else "w"
        with open(path, mode, encoding="utf-8") as f:
            for rec in records:
                f.write(rec.model_dump_json() + "\n")

    def load_feedback(self) -> list[FeedbackRecord]:
        path = self._dir / "feedback.jsonl"
        if not path.exists():
            return []
        records: list[FeedbackRecord] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(FeedbackRecord(**json.loads(line)))
        return records

    def save_tuning_config(self, config: TuningConfig) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / "tuning_config.json"
        path.write_text(config.model_dump_json(indent=2), encoding="utf-8")

    def load_tuning_config(self) -> TuningConfig | None:
        path = self._dir / "tuning_config.json"
        if not path.exists():
            return None
        return TuningConfig(**json.loads(path.read_text(encoding="utf-8")))


class TelemetryIngestor:
    """Ingests OpenTelemetry traces and maps them to symbol graph nodes."""

    def __init__(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
    ) -> None:
        self._nodes = nodes
        self._edges = edges
        self._name_index: dict[str, list[str]] = {}
        self._path_index: dict[str, list[str]] = {}
        for node in nodes:
            self._name_index.setdefault(node.name, []).append(node.id)
            key = node.path.lower()
            self._path_index.setdefault(key, []).append(node.id)

    def ingest_traces(self, spans: list[TraceSpan]) -> list[TraceSpan]:
        """Map trace spans to graph nodes."""
        mapped: list[TraceSpan] = []
        for span in spans:
            mapped_span = self._map_span(span)
            mapped.append(mapped_span)
        return mapped

    def compute_runtime_metadata(
        self,
        mapped_spans: list[TraceSpan],
    ) -> dict[str, RuntimeMetadata]:
        """Aggregate mapped spans into per-node runtime metadata."""
        groups: dict[str, list[TraceSpan]] = {}
        for span in mapped_spans:
            if span.mapped_node_id:
                groups.setdefault(span.mapped_node_id, []).append(span)

        metadata: dict[str, RuntimeMetadata] = {}
        for node_id, node_spans in groups.items():
            call_count = len(node_spans)
            error_count = sum(1 for s in node_spans if s.status_code == "ERROR")
            latencies = [self._span_duration_ms(s) for s in node_spans]
            latencies.sort()
            last_seen = max(s.end_time for s in node_spans) if node_spans else None

            metadata[node_id] = RuntimeMetadata(
                node_id=node_id,
                call_count=call_count,
                error_count=error_count,
                avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
                p50_latency_ms=self._percentile(latencies, 50),
                p95_latency_ms=self._percentile(latencies, 95),
                p99_latency_ms=self._percentile(latencies, 99),
                last_seen=last_seen,
                error_rate=error_count / call_count if call_count > 0 else 0.0,
            )
        return metadata

    def update_graph_metadata(
        self,
        runtime_meta: dict[str, RuntimeMetadata],
    ) -> dict[str, float]:
        """Derive runtime weight for each node: normalized call_count * (1 - error_rate)."""
        if not runtime_meta:
            return {}
        max_calls = max(m.call_count for m in runtime_meta.values())
        if max_calls == 0:
            return {nid: 0.0 for nid in runtime_meta}

        weights: dict[str, float] = {}
        for nid, meta in runtime_meta.items():
            norm = meta.call_count / max_calls
            weights[nid] = round(norm * (1.0 - meta.error_rate), 4)
        return weights

    def _map_span(self, span: TraceSpan) -> TraceSpan:
        """Try multiple strategies to map a span to a graph node."""
        # Strategy 1: Exact operation name match
        ids = self._name_index.get(span.operation_name, [])
        if ids:
            span.mapped_node_id = ids[0]
            span.mapping_confidence = MAPPING_CONFIDENCE["exact_name"]
            return span

        # Strategy 2: filepath attribute match
        filepath = span.attributes.get("code.filepath", "")
        if filepath:
            key = filepath.lower()
            path_ids = self._path_index.get(key, [])
            if path_ids:
                span.mapped_node_id = path_ids[0]
                span.mapping_confidence = MAPPING_CONFIDENCE["filepath_match"]
                return span

        # Strategy 3: function attribute match
        func_name = span.attributes.get("code.function", "")
        if func_name:
            func_ids = self._name_index.get(func_name, [])
            if func_ids:
                span.mapped_node_id = func_ids[0]
                span.mapping_confidence = MAPPING_CONFIDENCE["function_attribute"]
                return span

        # Strategy 4: Partial name match (operation_name contains a node name)
        op_lower = span.operation_name.lower()
        for name, ids in self._name_index.items():
            if name.lower() in op_lower or op_lower in name.lower():
                span.mapped_node_id = ids[0]
                span.mapping_confidence = MAPPING_CONFIDENCE["partial_name"]
                return span

        return span

    @staticmethod
    def _span_duration_ms(span: TraceSpan) -> float:
        try:
            start = datetime.fromisoformat(span.start_time)
            end = datetime.fromisoformat(span.end_time)
            return (end - start).total_seconds() * 1000
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _percentile(sorted_values: list[float], pct: int) -> float:
        if not sorted_values:
            return 0.0
        idx = max(0, int(len(sorted_values) * pct / 100) - 1)
        return sorted_values[min(idx, len(sorted_values) - 1)]
