"""Gold retrieval benchmarks for Phase 2.

These tests are intentionally small and deterministic. They do not benchmark
embedding quality; they lock down graph-aware retrieval behavior once semantic
search has selected reasonable seed entries.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from kb_agent.graph.storage import GraphStorage
from kb_agent.models.entry import AIData, KBEntry, Language, Layer, StaticData, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.query.engine import QueryEngine
from kb_agent.query.retrieval import RetrievalEngine


@dataclass(frozen=True)
class GoldQuery:
    name: str
    question: str
    seed_entry_ids: tuple[str, ...]
    expected_intent: str
    expected_seed_node_ids: tuple[str, ...]
    expected_expanded_node_ids: tuple[str, ...]
    expected_entry_ids: tuple[str, ...]
    expected_edge_tuples: tuple[tuple[str, str, str], ...] = ()


GOLD_QUERIES: tuple[GoldQuery, ...] = (
    GoldQuery(
        name="symbol_lookup_retrieval_engine",
        question="What does RetrievalEngine do?",
        seed_entry_ids=("mem.kb_agent/query.retrieval.RetrievalEngine_L18",),
        expected_intent="symbol_lookup",
        expected_seed_node_ids=("repo/kb_agent/query/retrieval.py::RetrievalEngine",),
        expected_expanded_node_ids=(
            "repo/kb_agent/query/retrieval.py::RetrievalEngine",
            "repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve",
            "repo/kb_agent/query/retrieval.py::RetrievalEngine._get_mapper",
        ),
        expected_entry_ids=("mem.kb_agent/query.retrieval.RetrievalEngine_L18",),
        expected_edge_tuples=(
            (
                "repo/kb_agent/query/retrieval.py::RetrievalEngine",
                "repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve",
                EdgeKind.CONTAINS.value,
            ),
        ),
    ),
    GoldQuery(
        name="flow_trace_graph_retrieval",
        question="How does graph retrieval work?",
        seed_entry_ids=("mem.kb_agent/query.retrieval.retrievalengine.retrieve_L36",),
        expected_intent="flow_trace",
        expected_seed_node_ids=("repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve",),
        expected_expanded_node_ids=(
            "repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve",
            "repo/kb_agent/query/intent.py::classify_intent",
            "repo/kb_agent/query/expander.py::expand_from_seeds",
            "repo/kb_agent/query/composer.py::compose_context",
        ),
        expected_entry_ids=("mem.kb_agent/query.retrieval.retrievalengine.retrieve_L36",),
        expected_edge_tuples=(
            (
                "repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve",
                "repo/kb_agent/query/expander.py::expand_from_seeds",
                EdgeKind.CALLS.value,
            ),
            (
                "repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve",
                "repo/kb_agent/query/composer.py::compose_context",
                EdgeKind.CALLS.value,
            ),
        ),
    ),
    GoldQuery(
        name="module_overview_query",
        question="overview of query module",
        seed_entry_ids=("mod.kb_agent/query",),
        expected_intent="module_overview",
        expected_seed_node_ids=(),
        expected_expanded_node_ids=(),
        expected_entry_ids=("mod.kb_agent/query",),
    ),
    GoldQuery(
        name="relationship_compose_context",
        question="Who calls compose_context?",
        seed_entry_ids=("mem.kb_agent/query.composer.compose_context_L35",),
        expected_intent="relationship",
        expected_seed_node_ids=("repo/kb_agent/query/composer.py::compose_context",),
        expected_expanded_node_ids=(
            "repo/kb_agent/query/composer.py::compose_context",
            "repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve",
        ),
        expected_entry_ids=("mem.kb_agent/query.composer.compose_context_L35",),
        expected_edge_tuples=(
            (
                "repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve",
                "repo/kb_agent/query/composer.py::compose_context",
                EdgeKind.CALLS.value,
            ),
        ),
    ),
)


def _node(
    node_id: str,
    name: str,
    kind: SymbolKind,
    path: str,
    line_start: int,
    line_end: int,
    signature: str,
) -> SymbolNode:
    return SymbolNode(
        id=node_id,
        name=name,
        kind=kind,
        language=Language.PYTHON,
        path=path,
        line_start=line_start,
        line_end=line_end,
        signature=signature,
    )


def _edge(source: str, target: str, kind: EdgeKind, confidence: float = 0.85) -> SymbolEdge:
    return SymbolEdge(
        source=source,
        target=target,
        kind=kind,
        confidence=confidence,
        source_type="heuristic",
        resolution="benchmark",
    )


def _entry(
    entry_id: str,
    layer: Layer,
    path: str,
    line_start: int,
    summary: str,
    kind: SymbolKind = SymbolKind.FUNCTION,
) -> KBEntry:
    return KBEntry(
        id=entry_id,
        layer=layer,
        static=StaticData(
            kind=kind,
            language=Language.PYTHON,
            path=path,
            line_start=line_start,
            line_end=line_start + 10,
            signature=summary,
        ),
        ai=AIData(summary=summary, confidence=0.9),
    )


@pytest.fixture
def retrieval_benchmark_kb(tmp_path: Path):
    ids = {
        "engine": "repo/kb_agent/query/retrieval.py::RetrievalEngine",
        "init": "repo/kb_agent/query/retrieval.py::RetrievalEngine.__init__",
        "retrieve": "repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve",
        "mapper": "repo/kb_agent/query/retrieval.py::RetrievalEngine._get_mapper",
        "query_engine": "repo/kb_agent/query/engine.py::QueryEngine",
        "classify": "repo/kb_agent/query/intent.py::classify_intent",
        "map_entries": "repo/kb_agent/query/mapper.py::build_entry_to_node_mapper",
        "expand": "repo/kb_agent/query/expander.py::expand_from_seeds",
        "compose": "repo/kb_agent/query/composer.py::compose_context",
    }
    nodes = [
        _node(ids["engine"], "RetrievalEngine", SymbolKind.CLASS, "kb_agent/query/retrieval.py", 18, 95, "class RetrievalEngine"),
        _node(ids["init"], "__init__", SymbolKind.METHOD, "kb_agent/query/retrieval.py", 25, 34, "def __init__(...)"),
        _node(ids["retrieve"], "retrieve", SymbolKind.METHOD, "kb_agent/query/retrieval.py", 36, 68, "def retrieve(...)"),
        _node(ids["mapper"], "_get_mapper", SymbolKind.METHOD, "kb_agent/query/retrieval.py", 71, 75, "def _get_mapper(...)"),
        _node(ids["query_engine"], "QueryEngine", SymbolKind.CLASS, "kb_agent/query/engine.py", 14, 74, "class QueryEngine"),
        _node(ids["classify"], "classify_intent", SymbolKind.FUNCTION, "kb_agent/query/intent.py", 43, 56, "def classify_intent(...)"),
        _node(ids["map_entries"], "build_entry_to_node_mapper", SymbolKind.FUNCTION, "kb_agent/query/mapper.py", 19, 51, "def build_entry_to_node_mapper(...)"),
        _node(ids["expand"], "expand_from_seeds", SymbolKind.FUNCTION, "kb_agent/query/expander.py", 28, 91, "def expand_from_seeds(...)"),
        _node(ids["compose"], "compose_context", SymbolKind.FUNCTION, "kb_agent/query/composer.py", 35, 128, "def compose_context(...)"),
    ]
    edges = [
        _edge(ids["engine"], ids["init"], EdgeKind.CONTAINS, 1.0),
        _edge(ids["engine"], ids["retrieve"], EdgeKind.CONTAINS, 1.0),
        _edge(ids["engine"], ids["mapper"], EdgeKind.CONTAINS, 1.0),
        _edge(ids["init"], ids["query_engine"], EdgeKind.CALLS, 0.75),
        _edge(ids["retrieve"], ids["classify"], EdgeKind.CALLS, 0.80),
        _edge(ids["retrieve"], ids["map_entries"], EdgeKind.CALLS, 0.75),
        _edge(ids["retrieve"], ids["expand"], EdgeKind.CALLS, 0.85),
        _edge(ids["retrieve"], ids["compose"], EdgeKind.CALLS, 0.85),
        _edge(ids["mapper"], ids["query_engine"], EdgeKind.USES_TYPE, 0.80),
    ]
    GraphStorage(tmp_path / "graph").save(nodes, edges)

    entries = {
        "mem.kb_agent/query.retrieval.RetrievalEngine_L18": _entry(
            "mem.kb_agent/query.retrieval.RetrievalEngine_L18",
            Layer.MEM,
            "kb_agent/query/retrieval.py",
            18,
            "RetrievalEngine orchestrates semantic search, graph expansion, and context composition.",
            SymbolKind.CLASS,
        ),
        "mem.kb_agent/query.retrieval.retrievalengine.retrieve_L36": _entry(
            "mem.kb_agent/query.retrieval.retrievalengine.retrieve_L36",
            Layer.MEM,
            "kb_agent/query/retrieval.py",
            36,
            "retrieve runs the graph-aware retrieval pipeline.",
            SymbolKind.METHOD,
        ),
        "mem.kb_agent/query.composer.compose_context_L35": _entry(
            "mem.kb_agent/query.composer.compose_context_L35",
            Layer.MEM,
            "kb_agent/query/composer.py",
            35,
            "compose_context builds the final context payload.",
        ),
        "mod.kb_agent/query": _entry(
            "mod.kb_agent/query",
            Layer.MOD,
            "kb_agent/query",
            0,
            "Query module contains intent classification, semantic query, graph expansion, and context composition.",
            SymbolKind.MODULE,
        ),
    }

    return tmp_path, entries, nodes, edges


@pytest.mark.parametrize("gold", GOLD_QUERIES, ids=[g.name for g in GOLD_QUERIES])
def test_gold_retrieval_queries(gold: GoldQuery, retrieval_benchmark_kb):
    kb_dir, entries, _, _ = retrieval_benchmark_kb
    seed_entries = [entries[entry_id] for entry_id in gold.seed_entry_ids]

    with patch.object(QueryEngine, "query", return_value=seed_entries):
        result = RetrievalEngine(kb_dir).retrieve(gold.question, top_k=len(seed_entries))

    assert result.metrics.intent == gold.expected_intent
    assert {entry.id for entry in result.entries} == set(gold.expected_entry_ids)
    assert set(gold.expected_seed_node_ids).issubset(result.metrics.seed_nodes)
    assert set(gold.expected_expanded_node_ids).issubset(result.metrics.expanded_nodes)
    if not gold.expected_seed_node_ids:
        assert result.metrics.seed_nodes == list(gold.expected_entry_ids)
    assert set(gold.expected_edge_tuples).issubset(result.metrics.relationship_edges)
