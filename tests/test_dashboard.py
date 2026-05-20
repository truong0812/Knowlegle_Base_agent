"""Tests for observability dashboard."""
from __future__ import annotations

from pathlib import Path

import pytest

from kb_agent.analyzer.dashboard import DashboardAnalyzer
from kb_agent.graph.storage import GraphStorage
from kb_agent.graph.telemetry import TelemetryStorage
from kb_agent.models.dashboard import GraphHealthMetrics, RetrievalAnalytics
from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.models.telemetry import FeedbackRecord


def _node(name: str, path: str = "svc.py", line: int = 1, conf: float = 1.0) -> SymbolNode:
    return SymbolNode(
        id=f"repo/{path}::{name}",
        name=name,
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        path=path,
        line_start=line,
        line_end=line + 5,
        confidence=conf,
    )


def _make_graph(dir_path: Path, nodes: list[SymbolNode], edges: list[SymbolEdge] | None = None) -> None:
    storage = GraphStorage(dir_path / "graph")
    storage.save(nodes, edges or [])


class TestDashboardAnalyzer:
    def test_graph_health_metrics(self, tmp_path: Path):
        nodes = [_node("a"), _node("b"), _node("c")]
        edges = [
            SymbolEdge(source="repo/svc.py::a", target="repo/svc.py::b", kind=EdgeKind.CALLS),
            SymbolEdge(source="repo/svc.py::b", target="repo/svc.py::c", kind=EdgeKind.CALLS),
        ]
        _make_graph(tmp_path, nodes, edges)
        analyzer = DashboardAnalyzer(tmp_path)
        health = analyzer.graph_health()
        assert health.total_nodes == 3
        assert health.total_edges == 2
        assert health.edge_density == pytest.approx(2 / 3, abs=0.01)

    def test_graph_health_empty_graph(self, tmp_path: Path):
        _make_graph(tmp_path, [])
        analyzer = DashboardAnalyzer(tmp_path)
        health = analyzer.graph_health()
        assert health.total_nodes == 0

    def test_graph_health_confidence_distribution(self, tmp_path: Path):
        nodes = [
            _node("a", conf=0.90),
            _node("b", conf=0.55),
            _node("c", conf=0.20),
        ]
        _make_graph(tmp_path, nodes)
        analyzer = DashboardAnalyzer(tmp_path)
        health = analyzer.graph_health()
        assert health.confidence_distribution["high"] == 1
        assert health.confidence_distribution["medium"] == 1
        assert health.confidence_distribution["low"] == 1

    def test_graph_health_orphan_nodes(self, tmp_path: Path):
        nodes = [_node("a"), _node("b"), _node("orphan")]
        edges = [SymbolEdge(source="repo/svc.py::a", target="repo/svc.py::b", kind=EdgeKind.CALLS)]
        _make_graph(tmp_path, nodes, edges)
        analyzer = DashboardAnalyzer(tmp_path)
        health = analyzer.graph_health()
        assert health.orphan_nodes == 1

    def test_graph_health_bridge_count(self, tmp_path: Path):
        nodes = [_node("a"), _node("b")]
        edges = [
            SymbolEdge(source="repo/svc.py::a", target="repo/svc.py::b", kind=EdgeKind.BRIDGES_TO),
        ]
        _make_graph(tmp_path, nodes, edges)
        analyzer = DashboardAnalyzer(tmp_path)
        health = analyzer.graph_health()
        assert health.bridge_count == 1
        assert health.cross_repo_edge_count == 0

    def test_graph_health_no_graph_dir(self, tmp_path: Path):
        analyzer = DashboardAnalyzer(tmp_path)
        health = analyzer.graph_health()
        assert health.total_nodes == 0

    def test_retrieval_analytics_no_telemetry(self, tmp_path: Path):
        analyzer = DashboardAnalyzer(tmp_path)
        analytics = analyzer.retrieval_analytics()
        assert analytics.feedback_total == 0

    def test_retrieval_analytics(self, tmp_path: Path):
        tel_dir = tmp_path / "telemetry"
        storage = TelemetryStorage(tel_dir)
        records = [
            FeedbackRecord(query="q1", response_node_ids=["n1"], useful=True),
            FeedbackRecord(query="q2", response_node_ids=["n2"], useful=False),
            FeedbackRecord(query="q3", response_node_ids=["n3"], useful=True),
        ]
        storage.save_feedback(records, append=False)

        analyzer = DashboardAnalyzer(tmp_path)
        analytics = analyzer.retrieval_analytics()
        assert analytics.feedback_total == 3
        assert analytics.feedback_useful_rate == pytest.approx(2 / 3, abs=0.01)

    def test_format_health_output(self):
        metrics = GraphHealthMetrics(
            total_nodes=100,
            total_edges=250,
            edge_density=2.5,
            avg_confidence=0.85,
            confidence_distribution={"high": 80, "medium": 15, "low": 5},
            orphan_nodes=3,
            orphan_ratio=0.03,
        )
        output = DashboardAnalyzer.format_health(metrics)
        assert "Nodes: 100" in output
        assert "Edges: 250" in output
        assert "Orphan nodes: 3" in output

    def test_format_analytics_output(self):
        metrics = RetrievalAnalytics(feedback_total=50, feedback_useful_rate=0.8)
        output = DashboardAnalyzer.format_analytics(metrics)
        assert "Feedback total: 50" in output
        assert "80.0%" in output
