"""Tests for deterministic feature overlay (Phase 2, Step 3)."""
from __future__ import annotations

import asyncio

import pytest

from kb_agent.models.entry import Language, Layer, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.graph.features import FeatureExtractor, Feature


def _make_node(name: str, node_id: str | None = None, path: str = "src/main.py") -> SymbolNode:
    return SymbolNode(
        id=node_id or f"repo/{path}::{name}()",
        name=name,
        kind=SymbolKind.FUNCTION,
        language=Language.PYTHON,
        path=path,
        line_start=1,
        line_end=10,
    )


def _make_edge(source: str, target: str) -> SymbolEdge:
    return SymbolEdge(
        source=source,
        target=target,
        kind=EdgeKind.CALLS,
        confidence=0.80,
    )


class TestNounExtraction:
    def test_snake_case(self):
        ext = FeatureExtractor([], [])
        nouns = ext.extract_nouns("validate_auth_token")
        assert "auth" in nouns
        assert "token" in nouns

    def test_camel_case(self):
        ext = FeatureExtractor([], [])
        nouns = ext.extract_nouns("getUserProfile")
        assert "user" in nouns
        assert "profile" in nouns

    def test_stop_words_filtered(self):
        ext = FeatureExtractor([], [])
        nouns = ext.extract_nouns("get_user")
        assert "user" in nouns
        assert "get" not in nouns

    def test_short_words_filtered(self):
        ext = FeatureExtractor([], [])
        nouns = ext.extract_nouns("do_x")
        assert nouns == []

    def test_single_word(self):
        ext = FeatureExtractor([], [])
        nouns = ext.extract_nouns("authenticate")
        assert "authenticate" in nouns

    def test_all_uppercase(self):
        ext = FeatureExtractor([], [])
        nouns = ext.extract_nouns("HTTPHandler")
        assert "handler" in nouns


class TestClusterBySharedNouns:
    def test_cluster_by_shared_noun(self):
        nodes = [
            _make_node("validate_auth"),
            _make_node("auth_token"),
            _make_node("auth_service"),
        ]
        # Need edges between them for structural connection
        edges = [
            _make_edge(nodes[0].id, nodes[1].id),
            _make_edge(nodes[1].id, nodes[2].id),
        ]
        ext = FeatureExtractor(nodes, edges)
        noun_map = ext.build_noun_to_nodes()
        assert "auth" in noun_map
        assert len(noun_map["auth"]) == 3

    def test_single_occurrence_noun_excluded(self):
        nodes = [
            _make_node("unique_thing"),
            _make_node("other_item"),
        ]
        ext = FeatureExtractor(nodes, [])
        noun_map = ext.build_noun_to_nodes()
        # "thing" and "item" each appear only once
        assert len(noun_map) == 0

    def test_utility_nodes_excluded(self):
        nodes = [
            _make_node("auth_logger"),
            _make_node("auth_config"),
        ]
        ext = FeatureExtractor(nodes, [])
        noun_map = ext.build_noun_to_nodes()
        # Both are utility names → excluded
        assert len(noun_map) == 0

    def test_no_cluster_without_edges(self):
        nodes = [
            _make_node("validate_auth"),
            _make_node("auth_token"),
        ]
        ext = FeatureExtractor(nodes, [])  # No edges
        features = ext.extract_features()
        assert len(features) == 0


class TestMergeOverlapping:
    def test_merge_high_overlap(self):
        nodes = [
            _make_node("validate_auth_token"),
            _make_node("create_auth_token"),
            _make_node("revoke_auth_token"),
        ]
        edges = [
            _make_edge(nodes[0].id, nodes[1].id),
            _make_edge(nodes[1].id, nodes[2].id),
        ]
        ext = FeatureExtractor(nodes, edges)
        features = ext.extract_features()
        # "auth" and "token" overlap completely → merged
        assert len(features) <= 2

    def test_no_merge_below_threshold(self):
        nodes = [
            _make_node("auth_validate"),
            _make_node("auth_login"),
            _make_node("payment_process"),
            _make_node("payment_charge"),
        ]
        edges = [
            _make_edge(nodes[0].id, nodes[1].id),
            _make_edge(nodes[2].id, nodes[3].id),
        ]
        ext = FeatureExtractor(nodes, edges)
        features = ext.extract_features()
        # "auth" and "payment" have no overlap → separate features
        assert len(features) == 2


class TestDeterminism:
    def test_reproducibility(self):
        """Run extract_features() 3 times, verify identical output."""
        nodes = [
            _make_node("auth_validate"),
            _make_node("auth_login"),
            _make_node("auth_logout"),
        ]
        edges = [
            _make_edge(nodes[0].id, nodes[1].id),
            _make_edge(nodes[1].id, nodes[2].id),
        ]

        results = []
        for _ in range(3):
            ext = FeatureExtractor(nodes, edges)
            features = ext.extract_features()
            results.append([(f.id, f.member_node_ids, f.edge_density) for f in features])

        assert results[0] == results[1] == results[2]


class TestEdgeDensity:
    def test_density_computed(self):
        nodes = [
            _make_node("auth_validate"),
            _make_node("auth_login"),
        ]
        edges = [
            _make_edge(nodes[0].id, nodes[1].id),
            _make_edge(nodes[1].id, nodes[0].id),
        ]
        ext = FeatureExtractor(nodes, edges)
        features = ext.extract_features()
        assert len(features) == 1
        assert features[0].edge_density >= 1

    def test_empty_graph_no_features(self):
        ext = FeatureExtractor([], [])
        assert ext.extract_features() == []


class TestFeatureStorage:
    def test_save_and_load(self, tmp_path):
        from kb_agent.graph.storage import GraphStorage

        storage = GraphStorage(tmp_path / "graph")
        features = [
            Feature(
                id="feature.auth",
                name="auth",
                member_node_ids=["n1", "n2", "n3"],
                naming_basis="auth",
                edge_density=5,
            ),
        ]
        storage.save_features(features)
        loaded = storage.load_features()
        assert len(loaded) == 1
        assert loaded[0].id == "feature.auth"
        assert loaded[0].member_node_ids == ["n1", "n2", "n3"]
        assert loaded[0].edge_density == 5

    def test_save_empty_features_truncates_stale_file(self, tmp_path):
        from kb_agent.graph.storage import GraphStorage

        storage = GraphStorage(tmp_path / "graph")
        storage.save_features([
            Feature(
                id="feature.auth",
                name="auth",
                member_node_ids=["n1"],
                naming_basis="auth",
                edge_density=1,
            ),
        ])
        storage.save_features([])

        assert storage.load_features() == []
        assert (tmp_path / "graph" / "features.jsonl").read_text(encoding="utf-8") == ""

    def test_load_nonexistent(self, tmp_path):
        from kb_agent.graph.storage import GraphStorage
        storage = GraphStorage(tmp_path / "graph")
        assert storage.load_features() == []


class TestFeatureView:
    def test_feature_view_uses_feature_layer(self):
        from kb_agent.views.base import ViewIDMapper
        from kb_agent.views.feature_view import FeatureViewBuilder

        nodes = [_make_node("auth_validate", node_id="n1")]
        feature = Feature(
            id="feature.auth",
            name="auth",
            member_node_ids=["n1"],
            naming_basis="auth",
            edge_density=1,
        )
        entries = asyncio.run(
            FeatureViewBuilder(ViewIDMapper(nodes, [])).build(
                features=[feature],
                nodes=nodes,
            )
        )

        assert len(entries) == 1
        assert entries[0].layer == Layer.FEATURE
        assert entries[0].static.source == "feature_overlay"
        assert entries[0].ai.summary
        assert "auth_validate" in entries[0].ai.summary
