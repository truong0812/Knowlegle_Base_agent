"""Tests for graph-aware embedding text enrichment."""
from __future__ import annotations

from pathlib import Path

import pytest

from kb_agent.graph.features import Feature
from kb_agent.graph.hotpath import HotPathScore
from kb_agent.indexer.graph_embedding import GraphAwareEmbedder
from kb_agent.models.entry import AIData, KBEntry, Layer, Language, StaticData, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode


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
    return SymbolEdge(source=src, target=tgt, kind=kind, confidence=0.8)


def _mem_entry(entry_id: str, path: str = "svc.py", line: int = 1, summary: str | None = None) -> KBEntry:
    return KBEntry(
        id=entry_id,
        layer=Layer.MEM,
        static=StaticData(
            kind=SymbolKind.FUNCTION,
            language=Language.PYTHON,
            path=path,
            line_start=line,
            line_end=line + 5,
            signature="def func()",
        ),
        ai=AIData(summary=summary),
    )


def _arch_entry(entry_id: str) -> KBEntry:
    return KBEntry(
        id=entry_id,
        layer=Layer.ARCH,
        static=StaticData(
            kind=SymbolKind.PACKAGE,
            language=Language.PYTHON,
            path=".",
            line_start=0,
            line_end=0,
        ),
    )


class TestGraphAwareEmbedder:
    def test_plain_text_fallback_no_graph(self):
        entry = _mem_entry("mem.svc.func_L1")
        embedder = GraphAwareEmbedder([], [])
        text = embedder.enrich_text(entry)
        assert "mem.svc.func_L1" in text
        assert "func()" in text

    def test_enriched_includes_calls(self):
        a = _node("func_a", "svc.py", 1)
        b = _node("func_b", "svc.py", 10)
        edges = [_edge(a.id, b.id)]
        embedder = GraphAwareEmbedder([a, b], edges)
        entry = _mem_entry("mem.svc.func_a_L1", path="svc.py", line=1)
        text = embedder.enrich_text(entry)
        assert "calls:" in text
        assert "func_b" in text

    def test_enriched_includes_callers(self):
        a = _node("func_a", "svc.py", 1)
        b = _node("func_b", "svc.py", 10)
        edges = [_edge(a.id, b.id)]
        embedder = GraphAwareEmbedder([a, b], edges)
        entry = _mem_entry("mem.svc.func_b_L10", path="svc.py", line=10)
        text = embedder.enrich_text(entry)
        assert "called by:" in text
        assert "func_a" in text

    def test_enriched_includes_features(self):
        node = _node("auth_handler", "svc.py", 1)
        features = [Feature(
            id="feature.auth",
            name="auth",
            member_node_ids=[node.id],
            naming_basis="auth",
            edge_density=1,
        )]
        embedder = GraphAwareEmbedder([node], [], features=features)
        entry = _mem_entry("mem.svc.auth_handler_L1", path="svc.py", line=1)
        text = embedder.enrich_text(entry)
        assert "features:" in text
        assert "auth" in text

    def test_enriched_includes_hotness(self):
        node = _node("hot_func", "svc.py", 1)
        hotpath = {node.id: HotPathScore(node_id=node.id, incoming_calls=5, hotness=1.0)}
        embedder = GraphAwareEmbedder([node], [], hotpath=hotpath)
        entry = _mem_entry("mem.svc.hot_func_L1", path="svc.py", line=1)
        text = embedder.enrich_text(entry)
        assert "hotness:" in text
        assert "1.00" in text

    def test_non_mem_entries_unchanged(self):
        node = _node("func_a", "svc.py", 1)
        embedder = GraphAwareEmbedder([node], [_edge(node.id, node.id)])
        entry = _arch_entry("arch.root")
        text = embedder.enrich_text(entry)
        assert "|" not in text or "arch.root" in text

    def test_missing_graph_data_graceful(self):
        entry = _mem_entry("mem.svc.orphan_L99", path="svc.py", line=99)
        embedder = GraphAwareEmbedder([], [])
        text = embedder.enrich_text(entry)
        # Should return base text without enrichment
        assert "mem.svc.orphan_L99" in text

    def test_enrichment_deterministic(self):
        a = _node("a", "svc.py", 1)
        b = _node("b", "svc.py", 10)
        edges = [_edge(a.id, b.id)]
        embedder = GraphAwareEmbedder([a, b], edges)
        entry = _mem_entry("mem.svc.a_L1", path="svc.py", line=1)
        text1 = embedder.enrich_text(entry)
        text2 = embedder.enrich_text(entry)
        assert text1 == text2

    def test_from_graph_dir_missing(self, tmp_path: Path):
        result = GraphAwareEmbedder.from_graph_dir(tmp_path / "nonexistent")
        assert result is None

    def test_from_graph_dir_present(self, tmp_path: Path):
        from kb_agent.graph.storage import GraphStorage
        node = _node("a", "svc.py", 1)
        storage = GraphStorage(tmp_path)
        storage.save([node], [])
        result = GraphAwareEmbedder.from_graph_dir(tmp_path)
        assert result is not None
