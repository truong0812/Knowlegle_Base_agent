"""RetrievalEngine — graph-aware retrieval orchestrator."""
from __future__ import annotations

import logging
from pathlib import Path

from kb_agent.graph.storage import GraphStorage
from kb_agent.query.composer import RetrievalMetrics, RetrievalResult, compose_context
from kb_agent.query.expander import expand_from_seeds
from kb_agent.query.intent import QueryIntent, classify_intent
from kb_agent.query.mapper import build_entry_to_node_mapper
from kb_agent.query.engine import QueryEngine
from kb_agent.views.base import ViewIDMapper

logger = logging.getLogger(__name__)


class RetrievalEngine:
    """Semantic search + graph expansion + context composition.

    Wraps QueryEngine for FAISS search, then enriches with graph context.
    Falls back to FAISS-only when no graph data is available.
    """

    def __init__(
        self,
        kb_dir: Path,
        model_name: str = "all-MiniLM-L6-v2",
        top_k: int = 5,
    ) -> None:
        self._kb_dir = kb_dir.resolve()
        self._query_engine = QueryEngine(kb_dir, model_name=model_name)
        self._top_k = top_k
        self._mapper: ViewIDMapper | None = None

    def retrieve(self, question: str, top_k: int | None = None) -> RetrievalResult:
        """Run full retrieval pipeline."""
        k = top_k or self._top_k
        intent = classify_intent(question)

        seed_entries = self._query_engine.query(question, top_k=k)
        if not seed_entries:
            return RetrievalResult(
                context="No results found.",
                entries=[],
                metrics=RetrievalMetrics(
                    query=question, intent=intent.value,
                    seed_nodes=[], expanded_nodes=[],
                    relationship_edges=[],
                    token_allocation={}, truncated=False,
                    truncated_nodes=[], total_tokens_used=0,
                ),
            )

        graph_dir = self._kb_dir / "graph"
        mapping = build_entry_to_node_mapper(seed_entries, graph_dir)

        if mapping is None or not mapping.seed_nodes:
            return self._entry_only_result(question, intent, seed_entries)

        mapper = self._get_mapper(graph_dir)
        subgraph = expand_from_seeds(mapping.seed_nodes, mapper)
        result = compose_context(
            subgraph=subgraph,
            seed_entries=seed_entries,
            unmapped_entries=mapping.unmapped_entries,
            intent=intent,
        )
        result.metrics.query = question
        return result

    def _get_mapper(self, graph_dir: Path) -> ViewIDMapper:
        if self._mapper is None:
            nodes, edges = GraphStorage(graph_dir).load()
            self._mapper = ViewIDMapper(nodes, edges)
        return self._mapper

    def _entry_only_result(
        self,
        question: str,
        intent: QueryIntent,
        entries: list[KBEntry],
    ) -> RetrievalResult:
        """Fallback: format FAISS results without graph expansion."""
        lines: list[str] = []
        for entry in entries:
            parts = [f"[{entry.layer.value}] {entry.id}"]
            if entry.static.signature:
                parts.append(f"  Signature: {entry.static.signature}")
            if entry.ai.summary:
                parts.append(f"  Summary: {entry.ai.summary}")
            parts.append(f"  Location: {entry.static.path}:{entry.static.line_start}")
            lines.append("\n".join(parts))

        context = "\n\n".join(lines)
        entry_ids = [e.id for e in entries]
        return RetrievalResult(
            context=context,
            entries=entries,
            metrics=RetrievalMetrics(
                query=question, intent=intent.value,
                seed_nodes=entry_ids, expanded_nodes=entry_ids,
                relationship_edges=[],
                token_allocation={"entry": len(context) // 4},
                truncated=False, truncated_nodes=[],
                total_tokens_used=len(context) // 4,
            ),
        )
