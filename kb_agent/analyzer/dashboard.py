"""Observability dashboard: graph health, retrieval analytics, debug tracing."""
from __future__ import annotations

import logging
from pathlib import Path

from kb_agent.graph.storage import GraphStorage
from kb_agent.models.dashboard import DebugInfo, GraphHealthMetrics, RetrievalAnalytics
from kb_agent.models.graph import EdgeKind

logger = logging.getLogger(__name__)


class DashboardAnalyzer:
    """Compute observability metrics from KB data."""

    def __init__(self, kb_dir: Path) -> None:
        self._kb_dir = kb_dir.resolve()

    def graph_health(self) -> GraphHealthMetrics:
        """Compute graph health metrics from .kb/graph/ data."""
        graph_dir = self._kb_dir / "graph"
        if not graph_dir.exists():
            return GraphHealthMetrics()

        storage = GraphStorage(graph_dir)
        nodes, edges = storage.load()
        if not nodes:
            return GraphHealthMetrics()

        # Edge density
        edge_density = len(edges) / len(nodes) if nodes else 0.0

        # Confidence distribution
        high = sum(1 for n in nodes if n.confidence >= 0.7)
        medium = sum(1 for n in nodes if 0.4 <= n.confidence < 0.7)
        low = sum(1 for n in nodes if n.confidence < 0.4)
        avg_conf = sum(n.confidence for n in nodes) / len(nodes)

        # Orphan nodes (no edges)
        connected = set()
        for edge in edges:
            connected.add(edge.source)
            connected.add(edge.target)
        orphans = len(nodes) - len(connected)

        # Edge kind distribution
        kind_dist: dict[str, int] = {}
        bridge_count = 0
        cross_repo = 0
        for edge in edges:
            kind_dist[edge.kind.value] = kind_dist.get(edge.kind.value, 0) + 1
            if edge.kind == EdgeKind.BRIDGES_TO:
                bridge_count += 1
            if edge.kind == EdgeKind.REFERENCES_REPO:
                cross_repo += 1

        return GraphHealthMetrics(
            total_nodes=len(nodes),
            total_edges=len(edges),
            edge_density=round(edge_density, 2),
            avg_confidence=round(avg_conf, 3),
            confidence_distribution={"high": high, "medium": medium, "low": low},
            orphan_nodes=orphans,
            orphan_ratio=round(orphans / len(nodes), 3) if nodes else 0.0,
            edge_kind_distribution=kind_dist,
            bridge_count=bridge_count,
            cross_repo_edge_count=cross_repo,
        )

    def retrieval_analytics(self) -> RetrievalAnalytics:
        """Compute retrieval analytics from telemetry data."""
        tel_dir = self._kb_dir / "telemetry"
        if not tel_dir.exists():
            return RetrievalAnalytics()

        from kb_agent.graph.telemetry import TelemetryStorage
        storage = TelemetryStorage(tel_dir)

        feedback = storage.load_feedback()
        total = len(feedback)
        useful = sum(1 for f in feedback if f.useful)

        return RetrievalAnalytics(
            feedback_total=total,
            feedback_useful_rate=useful / total if total > 0 else 0.0,
        )

    def debug_retrieval(
        self,
        question: str,
        top_k: int = 5,
    ) -> DebugInfo | None:
        """Run retrieval with detailed tracing enabled."""
        graph_dir = self._kb_dir / "graph"
        if not graph_dir.exists():
            return None

        try:
            from kb_agent.query.retrieval import RetrievalEngine
            engine = RetrievalEngine(self._kb_dir, top_k=top_k)
            result = engine.retrieve(question, top_k=top_k)

            return DebugInfo(
                query=question,
                intent=result.metrics.intent,
                seed_nodes=result.metrics.seed_nodes,
                expansion_path=result.metrics.expanded_nodes,
                suppression_log=[],
                edge_follow_log=[
                    f"{s}--{k}-->{t}"
                    for s, t, k in result.metrics.relationship_edges
                ],
                token_budget_breakdown=result.metrics.token_allocation,
            )
        except Exception as e:
            logger.error("Debug retrieval failed: %s", e)
            return DebugInfo(query=question, intent="error", suppression_log=[str(e)])

    @staticmethod
    def format_health(metrics: GraphHealthMetrics) -> str:
        """Format health metrics as human-readable text."""
        lines = [
            "=== Graph Health ===",
            f"  Nodes: {metrics.total_nodes}",
            f"  Edges: {metrics.total_edges}",
            f"  Edge density: {metrics.edge_density:.2f} edges/node",
            f"  Avg confidence: {metrics.avg_confidence:.3f}",
            f"  Confidence: high={metrics.confidence_distribution.get('high', 0)} "
            f"medium={metrics.confidence_distribution.get('medium', 0)} "
            f"low={metrics.confidence_distribution.get('low', 0)}",
            f"  Orphan nodes: {metrics.orphan_nodes} ({metrics.orphan_ratio:.1%})",
            f"  Bridges: {metrics.bridge_count}",
            f"  Cross-repo edges: {metrics.cross_repo_edge_count}",
            "",
            "  Edge kinds:",
        ]
        for kind, count in sorted(metrics.edge_kind_distribution.items()):
            lines.append(f"    {kind}: {count}")
        return "\n".join(lines)

    @staticmethod
    def format_analytics(metrics: RetrievalAnalytics) -> str:
        """Format retrieval analytics as human-readable text."""
        lines = [
            "=== Retrieval Analytics ===",
            f"  Feedback total: {metrics.feedback_total}",
            f"  Useful rate: {metrics.feedback_useful_rate:.1%}",
        ]
        return "\n".join(lines)

    @staticmethod
    def format_debug(info: DebugInfo) -> str:
        """Format debug trace as human-readable text."""
        lines = [
            "=== Debug Trace ===",
            f"  Query: {info.query}",
            f"  Intent: {info.intent}",
            f"  Seed nodes ({len(info.seed_nodes)}):",
        ]
        for nid in info.seed_nodes[:10]:
            lines.append(f"    {nid}")
        if info.expansion_path:
            lines.append(f"  Expanded ({len(info.expansion_path)}):")
            for nid in info.expansion_path[:20]:
                lines.append(f"    {nid}")
        if info.edge_follow_log:
            lines.append(f"  Edges followed ({len(info.edge_follow_log)}):")
            for entry in info.edge_follow_log[:20]:
                lines.append(f"    {entry}")
        if info.suppression_log:
            lines.append(f"  Suppressions ({len(info.suppression_log)}):")
            for entry in info.suppression_log[:10]:
                lines.append(f"    {entry}")
        return "\n".join(lines)
