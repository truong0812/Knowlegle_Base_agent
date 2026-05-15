"""Tests for retrieval engine — intent, mapper, expander, composer, integration."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

import pytest

from kb_agent.models.entry import AIData, KBEntry, Language, Layer, StaticData, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.views.base import ViewIDMapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(
    name: str = "func",
    kind: SymbolKind = SymbolKind.FUNCTION,
    path: str = "src/main.py",
    line_start: int = 1,
    line_end: int = 10,
    signature: str | None = "def func()",
    language: Language = Language.PYTHON,
) -> SymbolNode:
    return SymbolNode(
        id=f"repo/{path}::{name}",
        name=name,
        kind=kind,
        language=language,
        path=path,
        line_start=line_start,
        line_end=line_end,
        signature=signature,
    )


def _make_edge(
    source: str,
    target: str,
    kind: EdgeKind = EdgeKind.CALLS,
    confidence: float = 0.80,
    resolution: str = "direct_import",
) -> SymbolEdge:
    return SymbolEdge(
        source=source,
        target=target,
        kind=kind,
        confidence=confidence,
        source_type="heuristic",
        resolution=resolution,
    )


def _make_entry(
    entry_id: str,
    layer: Layer,
    path: str = "src/main.py",
    line_start: int = 1,
    summary: str = "test summary",
) -> KBEntry:
    return KBEntry(
        id=entry_id,
        layer=layer,
        static=StaticData(
            kind=SymbolKind.FUNCTION,
            language=Language.PYTHON,
            path=path,
            line_start=line_start,
            line_end=line_start + 10,
            signature="def func()",
        ),
        ai=AIData(summary=summary, confidence=0.8),
    )


def _build_mapper(
    nodes: list[SymbolNode],
    edges: list[SymbolEdge],
) -> ViewIDMapper:
    return ViewIDMapper(nodes, edges)


# ===========================================================================
# TestIntentClassification
# ===========================================================================

class TestIntentClassification:
    def test_symbol_lookup(self):
        from kb_agent.query.intent import QueryIntent, classify_intent
        assert classify_intent("What does login do?") == QueryIntent.SYMBOL_LOOKUP
        assert classify_intent("explain the auth service") == QueryIntent.SYMBOL_LOOKUP

    def test_flow_trace(self):
        from kb_agent.query.intent import QueryIntent, classify_intent
        assert classify_intent("How does authentication work?") == QueryIntent.FLOW_TRACE
        assert classify_intent("trace the login flow") == QueryIntent.FLOW_TRACE

    def test_module_overview(self):
        from kb_agent.query.intent import QueryIntent, classify_intent
        assert classify_intent("overview of src/services") == QueryIntent.MODULE_OVERVIEW

    def test_relationship(self):
        from kb_agent.query.intent import QueryIntent, classify_intent
        assert classify_intent("What uses the login function?") == QueryIntent.RELATIONSHIP
        assert classify_intent("callers of authenticate") == QueryIntent.RELATIONSHIP

    def test_default(self):
        from kb_agent.query.intent import QueryIntent, classify_intent
        assert classify_intent("login") == QueryIntent.DEFAULT
        assert classify_intent("auth middleware") == QueryIntent.DEFAULT

    def test_specificity_ordering(self):
        from kb_agent.query.intent import QueryIntent, classify_intent
        assert classify_intent("What uses the config?") == QueryIntent.RELATIONSHIP


# ===========================================================================
# TestEntryNodeMapper
# ===========================================================================

class TestEntryNodeMapper:
    def test_maps_mem_entry_to_node(self, tmp_path: Path):
        from kb_agent.graph.storage import GraphStorage
        from kb_agent.query.mapper import build_entry_to_node_mapper

        node = _make_node("login", path="src/auth.py", line_start=10)
        edge = _make_edge(node.id, "repo/src/db.py::connect")
        GraphStorage(tmp_path / "graph").save([node, _make_node("connect", path="src/db.py", line_start=5)], [edge])

        entry = _make_entry("mem.auth.login_L10", Layer.MEM, path="src/auth.py", line_start=10)
        result = build_entry_to_node_mapper([entry], tmp_path / "graph")

        assert result is not None
        assert len(result.seed_nodes) == 1
        assert result.seed_nodes[0].name == "login"
        assert len(result.unmapped_entries) == 0

    def test_returns_none_when_no_graph(self, tmp_path: Path):
        from kb_agent.query.mapper import build_entry_to_node_mapper

        entry = _make_entry("mem.test.x", Layer.MEM)
        result = build_entry_to_node_mapper([entry], tmp_path / "nonexistent")
        assert result is None

    def test_non_mem_entries_unmapped(self, tmp_path: Path):
        from kb_agent.graph.storage import GraphStorage
        from kb_agent.query.mapper import build_entry_to_node_mapper

        node = _make_node("x", path="src/a.py", line_start=1)
        GraphStorage(tmp_path / "graph").save([node], [])

        arch = _make_entry("arch.root", Layer.ARCH, path="src/a.py", line_start=1)
        result = build_entry_to_node_mapper([arch], tmp_path / "graph")

        assert result is not None
        assert len(result.seed_nodes) == 0
        assert len(result.unmapped_entries) == 1

    def test_collision_prefers_narrower_range(self, tmp_path: Path):
        from kb_agent.graph.storage import GraphStorage
        from kb_agent.query.mapper import build_entry_to_node_mapper

        wide = _make_node("wide", path="a.py", line_start=1, line_end=50)
        narrow = _make_node("narrow", path="a.py", line_start=1, line_end=10)
        GraphStorage(tmp_path / "graph").save([wide, narrow], [])

        entry = _make_entry("mem.a.narrow_L1", Layer.MEM, path="a.py", line_start=1)
        result = build_entry_to_node_mapper([entry], tmp_path / "graph")

        assert result is not None
        assert result.seed_nodes[0].name == "narrow"


# ===========================================================================
# TestGraphExpander
# ===========================================================================

class TestGraphExpander:
    def test_single_seed_no_edges(self):
        from kb_agent.query.expander import expand_from_seeds

        node = _make_node("solo")
        mapper = _build_mapper([node], [])
        subgraph = expand_from_seeds([node], mapper)

        assert len(subgraph.seed_nodes) == 1
        assert len(subgraph.hop1_nodes) == 0
        assert len(subgraph.hop2_nodes) == 0

    def test_one_hop_expansion(self):
        from kb_agent.query.expander import expand_from_seeds

        a = _make_node("a", line_start=1)
        b = _make_node("b", path="src/util.py", line_start=5)
        edge = _make_edge(a.id, b.id, confidence=0.80)
        mapper = _build_mapper([a, b], [edge])
        subgraph = expand_from_seeds([a], mapper)

        assert len(subgraph.seed_nodes) == 1
        assert len(subgraph.hop1_nodes) == 1
        assert subgraph.hop1_nodes[0].name == "b"

    def test_two_hop_expansion(self):
        from kb_agent.query.expander import expand_from_seeds

        a = _make_node("a", line_start=1)
        b = _make_node("b", path="src/b.py", line_start=1)
        c = _make_node("c", path="src/c.py", line_start=1)
        e1 = _make_edge(a.id, b.id, confidence=0.80)
        e2 = _make_edge(b.id, c.id, confidence=0.80)
        mapper = _build_mapper([a, b, c], [e1, e2])
        subgraph = expand_from_seeds([a], mapper)

        assert len(subgraph.seed_nodes) == 1
        assert len(subgraph.hop1_nodes) == 1
        assert len(subgraph.hop2_nodes) == 1
        assert subgraph.hop2_nodes[0].name == "c"

    def test_max_nodes_limit(self):
        from kb_agent.query.expander import expand_from_seeds

        nodes = [_make_node(f"n{i}", path=f"src/{i}.py", line_start=1) for i in range(20)]
        edges = [_make_edge(nodes[0].id, nodes[i].id, confidence=0.80) for i in range(1, 20)]
        mapper = _build_mapper(nodes, edges)
        subgraph = expand_from_seeds([nodes[0]], mapper, max_nodes=10, max_edges_per_node=20)

        assert len(subgraph.all_nodes) == 10

    def test_confidence_filter(self):
        from kb_agent.query.expander import expand_from_seeds

        a = _make_node("a", line_start=1)
        b = _make_node("b", path="src/b.py", line_start=1)
        edge = _make_edge(a.id, b.id, confidence=0.50)
        mapper = _build_mapper([a, b], [edge])
        subgraph = expand_from_seeds([a], mapper, min_confidence=0.60)

        assert len(subgraph.hop1_nodes) == 0

    def test_utility_suppression(self):
        from kb_agent.query.expander import expand_from_seeds

        a = _make_node("a", line_start=1)
        logger = _make_node("logger", path="src/log.py", line_start=1)
        edge = _make_edge(a.id, logger.id, confidence=0.80)
        mapper = _build_mapper([a, logger], [edge])
        subgraph = expand_from_seeds([a], mapper)

        assert len(subgraph.hop1_nodes) == 0

    def test_max_edges_per_node(self):
        from kb_agent.query.expander import expand_from_seeds

        a = _make_node("a", line_start=1)
        targets = [_make_node(f"t{i}", path=f"src/t{i}.py", line_start=1) for i in range(10)]
        edges = [_make_edge(a.id, t.id, confidence=0.70 + i * 0.01) for i, t in enumerate(targets)]
        mapper = _build_mapper([a] + targets, edges)
        subgraph = expand_from_seeds([a], mapper, max_edges_per_node=3, max_nodes=50)

        # Only top 3 edges by confidence should expand
        assert len(subgraph.hop1_nodes) == 3

    def test_bidirectional_expansion(self):
        from kb_agent.query.expander import expand_from_seeds

        caller = _make_node("caller", path="src/caller.py", line_start=1)
        target = _make_node("target", path="src/target.py", line_start=1)
        edge = _make_edge(caller.id, target.id, confidence=0.80)
        mapper = _build_mapper([caller, target], [edge])

        # Expanding from target should find caller via incoming edge
        subgraph = expand_from_seeds([target], mapper)
        assert len(subgraph.hop1_nodes) == 1
        assert subgraph.hop1_nodes[0].name == "caller"

    def test_no_duplicate_nodes(self):
        from kb_agent.query.expander import expand_from_seeds

        a = _make_node("a", line_start=1)
        b = _make_node("b", path="src/b.py", line_start=1)
        e1 = _make_edge(a.id, b.id, confidence=0.80)
        e2 = _make_edge(b.id, a.id, confidence=0.80)
        mapper = _build_mapper([a, b], [e1, e2])
        subgraph = expand_from_seeds([a], mapper)

        ids = [n.id for n in subgraph.all_nodes]
        assert len(ids) == len(set(ids))

    def test_edges_only_reference_included_nodes(self):
        from kb_agent.query.expander import expand_from_seeds

        nodes = [_make_node(f"n{i}", path=f"src/{i}.py", line_start=1) for i in range(20)]
        edges = [_make_edge(nodes[0].id, nodes[i].id, confidence=0.80) for i in range(1, 20)]
        mapper = _build_mapper(nodes, edges)
        subgraph = expand_from_seeds([nodes[0]], mapper, max_nodes=5, max_edges_per_node=20)

        included_ids = {n.id for n in subgraph.all_nodes}
        for edge in subgraph.relevant_edges:
            assert edge.source in included_ids, f"Edge source {edge.source} not in subgraph"
            assert edge.target in included_ids, f"Edge target {edge.target} not in subgraph"

    def test_seed_nodes_capped_by_max_nodes(self):
        from kb_agent.query.expander import expand_from_seeds

        seeds = [_make_node(f"s{i}", path=f"src/{i}.py", line_start=1) for i in range(20)]
        mapper = _build_mapper(seeds, [])
        subgraph = expand_from_seeds(seeds, mapper, max_nodes=5)

        assert len(subgraph.all_nodes) == 5
        assert len(subgraph.seed_nodes) == 5


# ===========================================================================
# TestContextComposer
# ===========================================================================

class TestContextComposer:
    def test_compose_with_empty_subgraph(self):
        from kb_agent.query.composer import compose_context
        from kb_agent.query.expander import ExpandedSubgraph
        from kb_agent.query.intent import QueryIntent

        subgraph = ExpandedSubgraph(seed_nodes=[], hop1_nodes=[], hop2_nodes=[])
        result = compose_context(subgraph, [], [], QueryIntent.DEFAULT)

        assert "No results" in result.context or result.context == ""

    def test_budget_allocation_by_intent(self):
        from kb_agent.query.composer import compose_context, TOTAL_TOKEN_BUDGET
        from kb_agent.query.expander import ExpandedSubgraph
        from kb_agent.query.intent import QueryIntent

        node = _make_node("login", line_start=1)
        subgraph = ExpandedSubgraph(seed_nodes=[node], hop1_nodes=[], hop2_nodes=[])

        result = compose_context(subgraph, [], [], QueryIntent.SYMBOL_LOOKUP)
        # SYMBOL_LOOKUP: entry gets 60% = 2400 tokens budget
        assert result.metrics.intent == "symbol_lookup"

    def test_entry_keeps_signature_when_truncated(self):
        from kb_agent.query.composer import compose_context
        from kb_agent.query.expander import ExpandedSubgraph
        from kb_agent.query.intent import QueryIntent

        node = _make_node("login", signature="def login(email, password) -> Token", line_start=1)
        subgraph = ExpandedSubgraph(seed_nodes=[node], hop1_nodes=[], hop2_nodes=[])

        result = compose_context(subgraph, [], [], QueryIntent.DEFAULT)
        assert "login" in result.context
        assert "def login" in result.context

    def test_edge_summary_format(self):
        from kb_agent.query.composer import compose_context
        from kb_agent.query.expander import ExpandedSubgraph
        from kb_agent.query.intent import QueryIntent

        a = _make_node("a", path="src/a.py", line_start=1)
        b = _make_node("b", path="src/b.py", line_start=1)
        edge = _make_edge(a.id, b.id, confidence=0.85)
        subgraph = ExpandedSubgraph(
            seed_nodes=[a], hop1_nodes=[b], hop2_nodes=[], relevant_edges=[edge],
        )

        result = compose_context(subgraph, [], [], QueryIntent.DEFAULT)
        assert "RELATIONSHIPS" in result.context
        assert "calls" in result.context
        assert "0.85" in result.context

    def test_metrics_populated(self):
        from kb_agent.query.composer import compose_context
        from kb_agent.query.expander import ExpandedSubgraph
        from kb_agent.query.intent import QueryIntent

        node = _make_node("fn", line_start=1)
        subgraph = ExpandedSubgraph(seed_nodes=[node], hop1_nodes=[], hop2_nodes=[])
        result = compose_context(subgraph, [], [], QueryIntent.DEFAULT)

        assert result.metrics.intent == "default"
        assert len(result.metrics.seed_nodes) == 1
        assert isinstance(result.metrics.total_tokens_used, int)

    def test_no_duplicate_entries(self):
        from kb_agent.query.composer import compose_context
        from kb_agent.query.expander import ExpandedSubgraph
        from kb_agent.query.intent import QueryIntent

        node = _make_node("login", path="src/auth.py", line_start=10)
        subgraph = ExpandedSubgraph(seed_nodes=[node], hop1_nodes=[], hop2_nodes=[])

        mem_entry = _make_entry("mem.auth.login_L10", Layer.MEM, path="src/auth.py", line_start=10)
        arch_entry = _make_entry("arch.root", Layer.ARCH, path="src/auth.py", line_start=10)

        # unmapped_entries contains arch_entry; seed_entries contains both.
        # result.entries must not contain duplicates.
        result = compose_context(subgraph, [mem_entry, arch_entry], [arch_entry], QueryIntent.DEFAULT)

        entry_ids = [e.id for e in result.entries]
        assert len(entry_ids) == len(set(entry_ids))

    def test_edge_tokens_counted_in_budget(self):
        from kb_agent.query.composer import compose_context, TOTAL_TOKEN_BUDGET
        from kb_agent.query.expander import ExpandedSubgraph
        from kb_agent.query.intent import QueryIntent

        a = _make_node("a", path="src/a.py", line_start=1)
        b = _make_node("b", path="src/b.py", line_start=1)
        edge = _make_edge(a.id, b.id, confidence=0.85)
        subgraph = ExpandedSubgraph(seed_nodes=[a], hop1_nodes=[b], hop2_nodes=[], relevant_edges=[edge])

        result = compose_context(subgraph, [], [], QueryIntent.DEFAULT)

        assert "RELATIONSHIPS" in result.context
        assert result.metrics.total_tokens_used > 0

    def test_relationship_section_respects_budget(self):
        from kb_agent.query.composer import compose_context, TOTAL_TOKEN_BUDGET
        from kb_agent.query.expander import ExpandedSubgraph
        from kb_agent.query.intent import QueryIntent

        a = _make_node("a", path="src/a.py", line_start=1)
        # Create many edges to force a large relationship section
        edges = [
            _make_edge(a.id, f"repo/src/b{i}.py::n{i}", confidence=0.80)
            for i in range(100)
        ]
        subgraph = ExpandedSubgraph(seed_nodes=[a], hop1_nodes=[], hop2_nodes=[], relevant_edges=edges)

        result = compose_context(subgraph, [], [], QueryIntent.DEFAULT)

        # total_tokens_used must not exceed the budget
        assert result.metrics.total_tokens_used <= TOTAL_TOKEN_BUDGET


# ===========================================================================
# TestRetrievalEngine
# ===========================================================================

class TestRetrievalEngine:
    def _mock_model(self):
        return MagicMock(encode=lambda q, **kw: [[0.1] * 384])

    def _setup_index(self, tmp_path: Path, id_map: list[str]) -> None:
        """Write dummy FAISS index file + id_map so QueryEngine._load() passes."""
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True, exist_ok=True)
        (index_dir / "faiss.index").write_bytes(b"fake")
        (index_dir / "id_map.json").write_text(
            json.dumps(id_map), encoding="utf-8",
        )

    def test_fallback_without_graph(self, tmp_path: Path):
        from kb_agent.query.engine import QueryEngine
        from kb_agent.query.retrieval import RetrievalEngine

        entry = _make_entry("mem.test.fn_L1", Layer.MEM, path="src/a.py", line_start=1)
        entries_dir = tmp_path / "entries"
        entries_dir.mkdir()
        (entries_dir / (entry.id.replace(".", "_") + ".json")).write_text(
            entry.model_dump_json(), encoding="utf-8",
        )
        self._setup_index(tmp_path, ["mem.test.fn_L1"])

        mock_faiss = MagicMock()
        mock_index = MagicMock()
        mock_index.search.return_value = ([[0.5]], [[0]])
        mock_faiss.read_index.return_value = mock_index

        with patch.dict(sys.modules, {"faiss": mock_faiss}):
            with patch.object(QueryEngine, "_get_model", self._mock_model):
                engine = RetrievalEngine(tmp_path)
                result = engine.retrieve("test query")

        assert "mem.test.fn_L1" in result.context
        assert result.metrics.intent == "default"

    def test_full_pipeline_with_graph(self, tmp_path: Path):
        from kb_agent.graph.storage import GraphStorage
        from kb_agent.query.engine import QueryEngine
        from kb_agent.query.retrieval import RetrievalEngine

        node = _make_node("login", path="src/auth.py", line_start=10, line_end=20)
        other = _make_node("verify", path="src/auth.py", line_start=25, line_end=30)
        edge = _make_edge(node.id, other.id, confidence=0.80)
        GraphStorage(tmp_path / "graph").save([node, other], [edge])

        entry = _make_entry(
            "mem.auth.login_L10", Layer.MEM,
            path="src/auth.py", line_start=10, summary="login function",
        )
        entries_dir = tmp_path / "entries"
        entries_dir.mkdir()
        (entries_dir / (entry.id.replace(".", "_") + ".json")).write_text(
            entry.model_dump_json(), encoding="utf-8",
        )
        self._setup_index(tmp_path, ["mem.auth.login_L10"])

        mock_faiss = MagicMock()
        mock_index = MagicMock()
        mock_index.search.return_value = ([[0.5]], [[0]])
        mock_faiss.read_index.return_value = mock_index

        with patch.dict(sys.modules, {"faiss": mock_faiss}):
            with patch.object(QueryEngine, "_get_model", self._mock_model):
                engine = RetrievalEngine(tmp_path)
                result = engine.retrieve("what does login do?")

        assert "login" in result.context
        assert result.metrics.intent == "symbol_lookup"
        assert len(result.metrics.seed_nodes) == 1

    def test_empty_results(self, tmp_path: Path):
        from kb_agent.query.engine import QueryEngine
        from kb_agent.query.retrieval import RetrievalEngine

        self._setup_index(tmp_path, ["mem.test.x"])

        mock_faiss = MagicMock()
        mock_index = MagicMock()
        mock_index.search.return_value = ([[99.0]], [[-1]])
        mock_faiss.read_index.return_value = mock_index

        with patch.dict(sys.modules, {"faiss": mock_faiss}):
            with patch.object(QueryEngine, "_get_model", self._mock_model):
                engine = RetrievalEngine(tmp_path)
                result = engine.retrieve("nonexistent")

        assert result.context == "No results found."
