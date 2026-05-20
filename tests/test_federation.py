"""Tests for multi-repository federation."""
from __future__ import annotations

from pathlib import Path

import pytest

from kb_agent.graph.federation import FederatedGraphManager
from kb_agent.graph.storage import GraphStorage
from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode


def _node(name: str, path: str = "svc.py", line: int = 1, lang: Language = Language.PYTHON) -> SymbolNode:
    return SymbolNode(
        id=f"repo/{path}::{name}",
        name=name,
        kind=SymbolKind.FUNCTION,
        language=lang,
        path=path,
        line_start=line,
        line_end=line + 5,
    )


def _make_graph(dir_path: Path, nodes: list[SymbolNode], edges: list[SymbolEdge] | None = None) -> None:
    storage = GraphStorage(dir_path / "graph")
    storage.save(nodes, edges or [])


class TestFederatedGraphManager:
    def test_add_repository(self, tmp_path: Path):
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"
        _make_graph(other_dir, [_node("auth_service", path="auth.py")])

        fed = FederatedGraphManager(kb_dir)
        ref = fed.add_repository(str(other_dir), repo_name="auth-service")
        assert ref.repo_name == "auth-service"
        assert ref.node_count == 1

    def test_list_repositories(self, tmp_path: Path):
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"
        _make_graph(other_dir, [_node("svc")])

        fed = FederatedGraphManager(kb_dir)
        fed.add_repository(str(other_dir), repo_name="svc-repo")
        repos = fed.list_repositories()
        assert len(repos) == 1
        assert repos[0].repo_name == "svc-repo"

    def test_remove_repository(self, tmp_path: Path):
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"
        _make_graph(other_dir, [_node("svc")])

        fed = FederatedGraphManager(kb_dir)
        ref = fed.add_repository(str(other_dir))
        fed.remove_repository(ref.repo_id)
        assert len(fed.list_repositories()) == 0

    def test_remove_repository_purges_foreign_nodes_from_graph(self, tmp_path: Path):
        """Removing a repo also removes its materialized foreign nodes/edges from graph."""
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"

        foreign_node = _node("process_payment", path="payment.py")
        _make_graph(other_dir, [foreign_node])

        local_nodes = [_node("checkout", path="cart.py"), _node("process_payment", path="cart.py")]
        local_edges = [
            SymbolEdge(source="repo/cart.py::checkout", target="repo/cart.py::process_payment", kind=EdgeKind.CALLS),
        ]

        fed = FederatedGraphManager(kb_dir)
        ref = fed.add_repository(str(other_dir), repo_name="payment-service")

        result = fed.resolve_cross_repo_symbols(local_nodes, local_edges)
        assert len(result.foreign_nodes) >= 1

        # Materialize into graph storage
        all_nodes = local_nodes + result.foreign_nodes
        all_edges = local_edges + result.edges
        _make_graph(kb_dir, all_nodes, all_edges)

        # Verify foreign nodes are in graph
        storage = GraphStorage(kb_dir / "graph")
        nodes_before, edges_before = storage.load()
        foreign_before = [n for n in nodes_before if n.id.startswith(f"external/{ref.repo_id}/")]
        assert len(foreign_before) >= 1

        # Remove repo — should purge foreign nodes from graph
        fed.remove_repository(ref.repo_id)

        nodes_after, edges_after = storage.load()
        foreign_after = [n for n in nodes_after if n.id.startswith(f"external/{ref.repo_id}/")]
        assert len(foreign_after) == 0
        # Local nodes survive
        assert len(nodes_after) == len(local_nodes)
        # REFERENCES_REPO edges removed
        cross_edges = [e for e in edges_after if e.kind == EdgeKind.REFERENCES_REPO]
        assert len(cross_edges) == 0

    def test_no_cross_repo_edges_single_repo(self, tmp_path: Path):
        kb_dir = tmp_path / "kb"
        nodes = [_node("a"), _node("b")]
        edges = [SymbolEdge(source="repo/svc.py::a", target="repo/svc.py::b", kind=EdgeKind.CALLS)]

        fed = FederatedGraphManager(kb_dir)
        result = fed.resolve_cross_repo_symbols(nodes, edges)
        assert len(result.edges) == 0
        assert len(result.foreign_nodes) == 0

    def test_resolve_cross_repo_by_name_match(self, tmp_path: Path):
        """Local node 'process_payment' is CALLED locally — bridge to foreign node with same name."""
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"

        foreign_nodes = [_node("process_payment", path="payment.py")]
        _make_graph(other_dir, foreign_nodes)

        local_nodes = [_node("checkout", path="cart.py"), _node("process_payment", path="cart.py")]
        local_edges = [
            SymbolEdge(
                source="repo/cart.py::checkout",
                target="repo/cart.py::process_payment",
                kind=EdgeKind.CALLS,
                confidence=0.80,
            ),
        ]

        fed = FederatedGraphManager(kb_dir)
        ref = fed.add_repository(str(other_dir), repo_name="payment-service")

        result = fed.resolve_cross_repo_symbols(local_nodes, local_edges)
        assert len(result.edges) >= 1
        assert all(e.kind == EdgeKind.REFERENCES_REPO for e in result.edges)
        # Target should be namespaced with repo_id
        for e in result.edges:
            assert e.target.startswith(f"external/{ref.repo_id}/")

    def test_resolve_includes_foreign_nodes(self, tmp_path: Path):
        """FederationResult.foreign_nodes contains namespaced foreign nodes."""
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"

        foreign_node = _node("process_payment", path="payment.py")
        _make_graph(other_dir, [foreign_node])

        local_nodes = [_node("checkout", path="cart.py"), _node("process_payment", path="cart.py")]
        local_edges = [
            SymbolEdge(
                source="repo/cart.py::checkout",
                target="repo/cart.py::process_payment",
                kind=EdgeKind.CALLS,
                confidence=0.80,
            ),
        ]

        fed = FederatedGraphManager(kb_dir)
        ref = fed.add_repository(str(other_dir), repo_name="payment-service")

        result = fed.resolve_cross_repo_symbols(local_nodes, local_edges)
        assert len(result.foreign_nodes) >= 1
        for fn in result.foreign_nodes:
            assert fn.id.startswith(f"external/{ref.repo_id}/")
            assert fn.path.startswith(f"external/{ref.repo_id}/")

    def test_foreign_nodes_enable_expander_traversal(self, tmp_path: Path):
        """After saving nodes+edges, ViewIDMapper can find namespaced foreign nodes."""
        from kb_agent.views.base import ViewIDMapper

        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"

        foreign_node = _node("process_payment", path="payment.py")
        _make_graph(other_dir, [foreign_node])

        local_nodes = [_node("checkout", path="cart.py"), _node("process_payment", path="cart.py")]
        local_edges = [
            SymbolEdge(source="repo/cart.py::checkout", target="repo/cart.py::process_payment", kind=EdgeKind.CALLS),
        ]

        fed = FederatedGraphManager(kb_dir)
        ref = fed.add_repository(str(other_dir), repo_name="payment-service")
        result = fed.resolve_cross_repo_symbols(local_nodes, local_edges)

        all_nodes = local_nodes + result.foreign_nodes
        all_edges = local_edges + result.edges
        _make_graph(kb_dir, all_nodes, all_edges)

        storage = GraphStorage(kb_dir / "graph")
        loaded_nodes, loaded_edges = storage.load()
        mapper = ViewIDMapper(loaded_nodes, loaded_edges)
        # The namespaced foreign node should be reachable
        ns_ids = [n.id for n in result.foreign_nodes]
        assert len(ns_ids) >= 1
        assert ns_ids[0] in mapper.node_by_id

    def test_resolve_cross_repo_unresolved_import(self, tmp_path: Path):
        """Unresolved IMPORTS edge target matched to foreign node by name."""
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"

        foreign_nodes = [_node("process_payment", path="payment.py")]
        _make_graph(other_dir, foreign_nodes)

        local_nodes = [_node("checkout", path="cart.py")]
        local_edges = [
            SymbolEdge(
                source="repo/cart.py::checkout",
                target="unresolved_process_payment",
                kind=EdgeKind.IMPORTS,
                confidence=0.50,
            ),
        ]

        fed = FederatedGraphManager(kb_dir)
        ref = fed.add_repository(str(other_dir), repo_name="payment-service")

        result = fed.resolve_cross_repo_symbols(local_nodes, local_edges)
        assert len(result.edges) >= 1
        assert all(e.kind == EdgeKind.REFERENCES_REPO for e in result.edges)
        for e in result.edges:
            assert e.target.startswith(f"external/{ref.repo_id}/")

    def test_rebuild_regenerates_missing_federation_edges(self, tmp_path: Path):
        """After a graph rebuild, calling resolve again regenerates federation edges."""
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"

        foreign_node = _node("process_payment", path="payment.py")
        _make_graph(other_dir, [foreign_node])

        local_nodes = [_node("checkout", path="cart.py"), _node("process_payment", path="cart.py")]
        local_edges = [
            SymbolEdge(source="repo/cart.py::checkout", target="repo/cart.py::process_payment", kind=EdgeKind.CALLS),
        ]

        fed = FederatedGraphManager(kb_dir)
        fed.add_repository(str(other_dir), repo_name="payment-service")

        # First resolve
        result1 = fed.resolve_cross_repo_symbols(local_nodes, local_edges)
        assert len(result1.edges) >= 1

        # Simulate rebuild: new edges list does NOT contain REFERENCES_REPO edges
        rebuilt_edges = list(local_edges)
        result2 = fed.resolve_cross_repo_symbols(local_nodes, rebuilt_edges)
        assert len(result2.edges) >= 1

        # But if edges already contain the REFERENCES_REPO edges, no duplicates
        full_edges = local_edges + result1.edges
        result3 = fed.resolve_cross_repo_symbols(local_nodes, full_edges)
        assert len(result3.edges) == 0

    def test_load_foreign_graph(self, tmp_path: Path):
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"
        nodes = [_node("svc_a"), _node("svc_b")]
        edges = [SymbolEdge(source="repo/svc.py::svc_a", target="repo/svc.py::svc_b", kind=EdgeKind.CALLS)]
        _make_graph(other_dir, nodes, edges)

        fed = FederatedGraphManager(kb_dir)
        ref = fed.add_repository(str(other_dir))
        loaded_nodes, loaded_edges = fed.load_foreign_graph(ref.repo_id)
        assert len(loaded_nodes) == 2
        assert len(loaded_edges) == 1

    def test_add_nonexistent_repo_raises(self, tmp_path: Path):
        kb_dir = tmp_path / "kb"
        fed = FederatedGraphManager(kb_dir)
        with pytest.raises(FileNotFoundError):
            fed.add_repository(str(tmp_path / "nonexistent"))


class TestFederationNamespaceCollision:
    """Tests that foreign nodes don't collide with local nodes of same path/name."""

    def test_no_id_collision_same_path_and_name(self, tmp_path: Path):
        """Local and foreign both have src/service.py::process_payment — no overwrite."""
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"

        # Both repos have the exact same file path and function name
        local_node = _node("process_payment", path="src/service.py")
        foreign_node = _node("process_payment", path="src/service.py")
        _make_graph(other_dir, [foreign_node])

        local_nodes = [local_node, _node("checkout", path="cart.py")]
        local_edges = [
            SymbolEdge(
                source="repo/cart.py::checkout",
                target="repo/src/service.py::process_payment",
                kind=EdgeKind.CALLS,
            ),
        ]

        fed = FederatedGraphManager(kb_dir)
        ref = fed.add_repository(str(other_dir), repo_name="payment-svc")
        result = fed.resolve_cross_repo_symbols(local_nodes, local_edges)

        # Merge
        all_nodes = local_nodes + result.foreign_nodes
        all_ids = [n.id for n in all_nodes]
        # No duplicates — local and foreign have distinct IDs
        assert len(all_ids) == len(set(all_ids))
        # Local node keeps its original ID
        assert "repo/src/service.py::process_payment" in all_ids
        # Foreign node is namespaced with repo_id
        ns_foreign = [n for n in result.foreign_nodes]
        assert len(ns_foreign) >= 1
        assert ns_foreign[0].id.startswith(f"external/{ref.repo_id}/")

    def test_no_path_collision_same_file(self, tmp_path: Path):
        """Foreign node paths are prefixed so entries don't overwrite each other."""
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"

        foreign_node = _node("handler", path="app.py")
        _make_graph(other_dir, [foreign_node])

        local_node = _node("handler", path="app.py")
        local_nodes = [local_node, _node("main", path="main.py")]
        local_edges = [
            SymbolEdge(source="repo/main.py::main", target="repo/app.py::handler", kind=EdgeKind.CALLS),
        ]

        fed = FederatedGraphManager(kb_dir)
        ref = fed.add_repository(str(other_dir), repo_name="upstream")
        result = fed.resolve_cross_repo_symbols(local_nodes, local_edges)

        # Local node keeps original path
        assert local_node.path == "app.py"
        # Foreign node has namespaced path with repo_id
        if result.foreign_nodes:
            assert result.foreign_nodes[0].path == f"external/{ref.repo_id}/app.py"
            assert result.foreign_nodes[0].path != local_node.path

    def test_edge_targets_are_namespaced(self, tmp_path: Path):
        """REFERENCES_REPO edge targets point at namespaced foreign IDs."""
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"

        _make_graph(other_dir, [_node("auth", path="auth/handler.py")])

        local_nodes = [_node("gateway", path="api.py"), _node("auth", path="api.py")]
        local_edges = [
            SymbolEdge(source="repo/api.py::gateway", target="repo/api.py::auth", kind=EdgeKind.CALLS),
        ]

        fed = FederatedGraphManager(kb_dir)
        ref = fed.add_repository(str(other_dir), repo_name="auth-svc")
        result = fed.resolve_cross_repo_symbols(local_nodes, local_edges)

        for e in result.edges:
            assert e.target.startswith(f"external/{ref.repo_id}/")
            # Target must not collide with any local node ID
            assert e.target not in {n.id for n in local_nodes}


class TestSameNameRepoCollision:
    """Two repos with the same repo_name must still produce distinct namespaces."""

    def test_distinct_repo_ids_same_name(self, tmp_path: Path):
        """Two repos both named 'payment-service' get different repo_ids → no collision."""
        kb_dir = tmp_path / "kb"
        other_a = tmp_path / "other_a"
        other_b = tmp_path / "other_b"

        # Both foreign repos have a node named "process" but in different files
        _make_graph(other_a, [_node("process", path="alpha.py")])
        _make_graph(other_b, [_node("process", path="beta.py")])

        local_nodes = [_node("handler", path="main.py"), _node("process", path="main.py")]
        local_edges = [
            SymbolEdge(source="repo/main.py::handler", target="repo/main.py::process", kind=EdgeKind.CALLS),
        ]

        fed = FederatedGraphManager(kb_dir)
        ref_a = fed.add_repository(str(other_a), repo_name="payment-service")
        ref_b = fed.add_repository(str(other_b), repo_name="payment-service")

        # repo_ids must differ even though repo_names are identical
        assert ref_a.repo_id != ref_b.repo_id

        result = fed.resolve_cross_repo_symbols(local_nodes, local_edges)
        # Should get edges to both foreign repos
        assert len(result.edges) >= 2

        # Each foreign node gets a distinct namespaced ID
        foreign_ids = [fn.id for fn in result.foreign_nodes]
        assert len(foreign_ids) == len(set(foreign_ids)), f"Duplicate foreign IDs: {foreign_ids}"

        # Verify each is prefixed with its own repo_id
        for fn in result.foreign_nodes:
            assert fn.id.startswith("external/repo-")

        # The two repos' foreign nodes must not collide
        a_ids = {fn.id for fn in result.foreign_nodes if ref_a.repo_id in fn.id}
        b_ids = {fn.id for fn in result.foreign_nodes if ref_b.repo_id in fn.id}
        assert len(a_ids) >= 1, "No foreign nodes from repo A"
        assert len(b_ids) >= 1, "No foreign nodes from repo B"
        assert a_ids.isdisjoint(b_ids)


class TestFederationStorage:
    def test_persist_repos_roundtrip(self, tmp_path: Path):
        kb_dir = tmp_path / "kb"
        other_dir = tmp_path / "other_kb"
        _make_graph(other_dir, [_node("svc")])

        fed1 = FederatedGraphManager(kb_dir)
        fed1.add_repository(str(other_dir), repo_name="test-repo")

        fed2 = FederatedGraphManager(kb_dir)
        repos = fed2.list_repositories()
        assert len(repos) == 1
        assert repos[0].repo_name == "test-repo"
