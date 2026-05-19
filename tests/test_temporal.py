"""Tests for temporal graph versioning."""
from __future__ import annotations

from pathlib import Path

import pytest

from kb_agent.graph.temporal import TemporalGraphManager
from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.models.temporal import EdgeDiff, GraphVersion, NodeDiff, VersionDiff
from kb_agent.query.intent import QueryIntent, classify_intent
from kb_agent.query.temporal_query import TemporalQueryHandler


def _node(name: str, path: str = "svc.py", line: int = 1, sig: str | None = None) -> SymbolNode:
    return SymbolNode(
        id=f"repo/{path}::{name}",
        name=name,
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        path=path,
        line_start=line,
        line_end=line + 5,
        signature=sig,
    )


def _edge(src: str, tgt: str, kind: EdgeKind = EdgeKind.CALLS) -> SymbolEdge:
    return SymbolEdge(source=src, target=tgt, kind=kind, confidence=0.8)


@pytest.fixture
def graph_dir(tmp_path: Path) -> Path:
    return tmp_path / "graph"


class TestTemporalGraphManager:
    def test_save_and_load_snapshot(self, graph_dir: Path):
        manager = TemporalGraphManager(graph_dir)
        nodes = [_node("a"), _node("b")]
        edges = [_edge(nodes[0].id, nodes[1].id)]
        manager.save_snapshot("v1", nodes, edges, commit_hash="abc123")
        loaded_nodes, loaded_edges = manager.load_snapshot("v1")
        assert len(loaded_nodes) == 2
        assert len(loaded_edges) == 1

    def test_list_versions_sorted(self, graph_dir: Path):
        manager = TemporalGraphManager(graph_dir)
        manager.save_snapshot("v1", [_node("a")], [])
        manager.save_snapshot("v2", [_node("a"), _node("b")], [])
        versions = manager.list_versions()
        assert len(versions) == 2
        assert versions[0].version_id == "v1"
        assert versions[1].version_id == "v2"

    def test_latest_version(self, graph_dir: Path):
        manager = TemporalGraphManager(graph_dir)
        manager.save_snapshot("v1", [_node("a")], [])
        manager.save_snapshot("v2", [_node("b")], [])
        latest = manager.latest_version()
        assert latest is not None
        assert latest.version_id == "v2"

    def test_latest_version_empty(self, graph_dir: Path):
        manager = TemporalGraphManager(graph_dir)
        assert manager.latest_version() is None

    def test_diff_added_nodes(self, graph_dir: Path):
        manager = TemporalGraphManager(graph_dir)
        manager.save_snapshot("v1", [_node("a")], [])
        manager.save_snapshot("v2", [_node("a"), _node("b")], [])
        diff = manager.diff_versions("v1", "v2")
        assert _node_id("b") in diff.node_diff.added
        assert len(diff.node_diff.removed) == 0

    def test_diff_removed_nodes(self, graph_dir: Path):
        manager = TemporalGraphManager(graph_dir)
        manager.save_snapshot("v1", [_node("a"), _node("b")], [])
        manager.save_snapshot("v2", [_node("a")], [])
        diff = manager.diff_versions("v1", "v2")
        assert _node_id("b") in diff.node_diff.removed

    def test_diff_modified_nodes(self, graph_dir: Path):
        manager = TemporalGraphManager(graph_dir)
        manager.save_snapshot("v1", [_node("a", sig="def a()")], [])
        manager.save_snapshot("v2", [_node("a", sig="def a(x: int)")], [])
        diff = manager.diff_versions("v1", "v2")
        assert _node_id("a") in diff.node_diff.modified

    def test_diff_added_edges(self, graph_dir: Path):
        manager = TemporalGraphManager(graph_dir)
        a, b = _node("a"), _node("b")
        manager.save_snapshot("v1", [a, b], [])
        manager.save_snapshot("v2", [a, b], [_edge(a.id, b.id)])
        diff = manager.diff_versions("v1", "v2")
        assert len(diff.edge_diff.added) == 1

    def test_diff_removed_edges(self, graph_dir: Path):
        manager = TemporalGraphManager(graph_dir)
        a, b = _node("a"), _node("b")
        manager.save_snapshot("v1", [a, b], [_edge(a.id, b.id)])
        manager.save_snapshot("v2", [a, b], [])
        diff = manager.diff_versions("v1", "v2")
        assert len(diff.edge_diff.removed) == 1

    def test_diff_identical_versions(self, graph_dir: Path):
        manager = TemporalGraphManager(graph_dir)
        nodes = [_node("a")]
        manager.save_snapshot("v1", nodes, [])
        manager.save_snapshot("v2", nodes, [])
        diff = manager.diff_versions("v1", "v2")
        assert len(diff.node_diff.added) == 0
        assert len(diff.node_diff.removed) == 0
        assert len(diff.node_diff.modified) == 0

    def test_version_meta_stored(self, graph_dir: Path):
        manager = TemporalGraphManager(graph_dir)
        manager.save_snapshot("v1", [_node("a")], [], commit_hash="deadbeef")
        versions = manager.list_versions()
        assert versions[0].commit_hash == "deadbeef"
        assert versions[0].node_count == 1

    def test_temporal_query_intent(self):
        assert classify_intent("what changed since v1") == QueryIntent.VERSION_DIFF
        assert classify_intent("diff since last week") == QueryIntent.VERSION_DIFF
        assert classify_intent("what was added recently") == QueryIntent.VERSION_DIFF

    def test_format_diff_readable(self, graph_dir: Path):
        manager = TemporalGraphManager(graph_dir)
        a, b = _node("a"), _node("b")
        manager.save_snapshot("v1", [a], [])
        manager.save_snapshot("v2", [a, b], [_edge(a.id, b.id)])
        handler = TemporalQueryHandler(graph_dir)
        diff_result = handler.diff_versions("v1", "v2")
        text = TemporalQueryHandler.format_diff(diff_result)
        assert "Nodes added" in text
        assert "Edges added" in text

    def test_pipeline_saves_version(self, graph_dir: Path, tmp_path: Path):
        """AnalysisPipeline creates a versioned snapshot when build_graph=True."""
        from kb_agent.analyzer.pipeline import AnalysisPipeline
        from kb_agent.scanner.scanner import FileScanner

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "main.py").write_text("def hello(): pass\n", encoding="utf-8")

        out_dir = tmp_path / "kb"
        pipeline = AnalysisPipeline(
            repo_root=repo_dir, out_dir=out_dir,
            build_graph=True, version_id="test-v1",
        )
        import asyncio
        asyncio.run(pipeline.run())

        manager = TemporalGraphManager(out_dir / "graph")
        versions = manager.list_versions()
        assert any(v.version_id == "test-v1" for v in versions)


def _node_id(name: str) -> str:
    return f"repo/svc.py::{name}"
