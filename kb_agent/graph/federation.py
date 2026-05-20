"""Multi-repository federation: cross-repo symbol references and resolution."""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from kb_agent.graph.storage import GraphStorage
from kb_agent.models.federation import CrossRepoReference, FederationResult, RepositoryRef
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode

logger = logging.getLogger(__name__)


def _namespace_id(original_id: str, repo_id: str) -> str:
    """Prefix a foreign node ID with external/{repo_id}/ to avoid collisions."""
    return f"external/{repo_id}/{original_id}"


def _namespace_path(original_path: str, repo_id: str) -> str:
    """Prefix a foreign node path with external/{repo_id}/ to avoid collisions."""
    return f"external/{repo_id}/{original_path}"


class FederatedGraphManager:
    """Manage cross-repository symbol references and resolution."""

    def __init__(self, kb_dir: Path) -> None:
        self._kb_dir = kb_dir
        self._fed_dir = kb_dir / "federated"
        self._repos: list[RepositoryRef] = self._load_repos()
        # Foreign name indexes: repo_id -> {name: [original_node_ids]}
        self._foreign_indexes: dict[str, dict[str, list[str]]] = {}
        # Foreign node cache: repo_id -> {original_id: SymbolNode}
        self._foreign_nodes: dict[str, dict[str, SymbolNode]] = {}

    def add_repository(
        self,
        repo_path: str,
        repo_name: str | None = None,
    ) -> RepositoryRef:
        """Register an external repository by pointing to its .kb directory."""
        repo_dir = Path(repo_path).resolve()
        if not repo_dir.exists():
            raise FileNotFoundError(f"Repository KB directory not found: {repo_dir}")

        graph_dir = repo_dir / "graph"
        if not graph_dir.exists():
            raise FileNotFoundError(f"No graph data in: {graph_dir}")

        storage = GraphStorage(graph_dir)
        nodes, edges = storage.load()

        repo_id = f"repo-{uuid.uuid4().hex[:8]}"
        name = repo_name or repo_dir.parent.name

        ref = RepositoryRef(
            repo_id=repo_id,
            repo_path=str(repo_dir),
            repo_name=name,
            node_count=len(nodes),
            edge_count=len(edges),
        )

        # Build name index and node cache for this repo
        name_idx: dict[str, list[str]] = {}
        node_cache: dict[str, SymbolNode] = {}
        for node in nodes:
            name_idx.setdefault(node.name, []).append(node.id)
            node_cache[node.id] = node
        self._foreign_indexes[repo_id] = name_idx
        self._foreign_nodes[repo_id] = node_cache

        self._repos.append(ref)
        self._save_repos()
        self._save_cross_repo_refs(self._load_cross_repo_refs())

        return ref

    def remove_repository(self, repo_id: str) -> None:
        """Unregister a repository and remove its materialized nodes/edges from the graph."""
        self._repos = [r for r in self._repos if r.repo_id != repo_id]
        self._foreign_indexes.pop(repo_id, None)
        self._foreign_nodes.pop(repo_id, None)
        refs = [r for r in self._load_cross_repo_refs() if r.target_repo != repo_id and r.source_repo != repo_id]
        self._save_cross_repo_refs(refs)
        self._save_repos()
        self._purge_foreign_from_graph(repo_id)

    def list_repositories(self) -> list[RepositoryRef]:
        """List all registered repositories."""
        return list(self._repos)

    def resolve_cross_repo_symbols(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
    ) -> FederationResult:
        """Find cross-repo symbol references and create REFERENCES_REPO edges.

        Foreign nodes are namespaced on import to prevent collisions:
        - id:   ``external/{repo_id}/{original_id}``
        - path: ``external/{repo_id}/{original_path}``

        Deduplication is against the current graph edges.
        """
        if not self._repos:
            return FederationResult()

        # Ensure foreign indexes and node caches are loaded
        for ref in self._repos:
            if ref.repo_id not in self._foreign_indexes:
                self._load_foreign_index(ref)

        local_node_ids = {n.id for n in nodes}
        node_by_id = {n.id: n for n in nodes}

        # Dedup against current graph edges
        seen_pairs: set[tuple[str, str]] = {
            (e.source, e.target) for e in edges if e.kind == EdgeKind.REFERENCES_REPO
        }

        # Build a merged foreign name index: name -> [(repo_id, original_id)]
        foreign_merged: dict[str, list[tuple[str, str]]] = {}
        for repo_id, idx in self._foreign_indexes.items():
            for name, ids in idx.items():
                for fid in ids:
                    foreign_merged.setdefault(name, []).append((repo_id, fid))

        cross_edges: list[SymbolEdge] = []
        imported: set[tuple[str, str]] = set()  # (repo_id, original_id)
        edge_repo_map: dict[str, str] = {}  # ns_id -> repo_id

        for edge in edges:
            if edge.kind not in (EdgeKind.IMPORTS, EdgeKind.CALLS):
                continue

            source_node = node_by_id.get(edge.source)
            if not source_node:
                continue

            target_is_local = edge.target in local_node_ids

            if target_is_local:
                target_node = node_by_id.get(edge.target)
                target_name = target_node.name if target_node else None
            else:
                target_name = edge.target.split("::")[-1].split("(")[0] if "::" in edge.target else edge.target

            if not target_name:
                continue

            # Exact name match
            foreign_matches = foreign_merged.get(target_name, [])

            # Fallback: substring match for unresolved targets
            if not foreign_matches and not target_is_local:
                for fname, fids in foreign_merged.items():
                    if fname in target_name or target_name in fname:
                        foreign_matches = fids
                        break

            for repo_id, fid in foreign_matches:
                ns_id = _namespace_id(fid, repo_id)

                # Skip if the namespaced ID is already a local node (shouldn't happen)
                if ns_id in local_node_ids:
                    continue

                pair = (edge.source, ns_id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                conf = 0.60 if target_is_local else 0.50
                cross_edges.append(SymbolEdge(
                    source=edge.source,
                    target=ns_id,
                    kind=EdgeKind.REFERENCES_REPO,
                    confidence=conf,
                    source_type="heuristic",
                    resolution="cross_repo_name_match" if target_is_local else "cross_repo_unresolved",
                ))
                imported.add((repo_id, fid))
                edge_repo_map[ns_id] = repo_id

        # Collect foreign nodes, namespacing id and path using repo_id
        foreign_nodes: list[SymbolNode] = []
        for repo_id, fid in imported:
            node_cache = self._foreign_nodes.get(repo_id, {})
            fnode = node_cache.get(fid)
            if fnode:
                foreign_nodes.append(fnode.model_copy(update={
                    "id": _namespace_id(fid, repo_id),
                    "path": _namespace_path(fnode.path, repo_id),
                }))

        # Persist cross-repo references (append new ones)
        existing_refs = self._load_cross_repo_refs()
        existing_ref_pairs = {(r.source_node_id, r.target_node_id) for r in existing_refs}
        new_refs = []
        for e in cross_edges:
            if (e.source, e.target) not in existing_ref_pairs:
                new_refs.append(CrossRepoReference(
                    source_repo="local",
                    source_node_id=e.source,
                    target_repo=edge_repo_map.get(e.target, "unknown"),
                    target_node_id=e.target,
                    reference_kind="import",
                    confidence=e.confidence,
                ))
        self._save_cross_repo_refs(existing_refs + new_refs)

        if cross_edges:
            logger.info(
                "Federation: resolved %d cross-repo references, importing %d foreign nodes",
                len(cross_edges), len(foreign_nodes),
            )

        return FederationResult(edges=cross_edges, foreign_nodes=foreign_nodes)

    def update_shared_deps(self) -> list[CrossRepoReference]:
        """Re-scan all registered repos for updated shared library references."""
        refs = self._load_cross_repo_refs()
        for ref in self._repos:
            self._load_foreign_index(ref)
        return refs

    def load_foreign_graph(self, repo_id: str) -> tuple[list[SymbolNode], list[SymbolEdge]]:
        """Load the symbol graph from a registered external repository."""
        ref = next((r for r in self._repos if r.repo_id == repo_id), None)
        if not ref:
            raise ValueError(f"Repository not found: {repo_id}")
        storage = GraphStorage(Path(ref.repo_path) / "graph")
        return storage.load()

    def _load_foreign_index(self, ref: RepositoryRef) -> None:
        """Build name index and node cache for a foreign repository."""
        try:
            nodes, _ = self.load_foreign_graph(ref.repo_id)
            idx: dict[str, list[str]] = {}
            node_cache: dict[str, SymbolNode] = {}
            for node in nodes:
                idx.setdefault(node.name, []).append(node.id)
                node_cache[node.id] = node
            self._foreign_indexes[ref.repo_id] = idx
            self._foreign_nodes[ref.repo_id] = node_cache
        except Exception:
            logger.debug("Failed to load foreign index for %s", ref.repo_id, exc_info=True)

    def _find_repo_for_ns_target(self, ns_target: str) -> str:
        """Extract repo_id from a namespaced target like external/{repo_id}/..."""
        if ns_target.startswith("external/"):
            parts = ns_target.split("/", 2)
            if len(parts) >= 3:
                return parts[1]
        return "unknown"

    def _purge_foreign_from_graph(self, repo_id: str) -> None:
        """Remove materialized external/{repo_id}/ nodes and REFERENCES_REPO edges from graph."""
        from kb_agent.graph.storage import GraphStorage

        graph_dir = self._kb_dir / "graph"
        if not graph_dir.exists():
            return

        storage = GraphStorage(graph_dir)
        nodes, edges = storage.load()

        prefix = f"external/{repo_id}/"
        surviving_nodes = [n for n in nodes if not n.id.startswith(prefix)]
        surviving_edges = [
            e for e in edges
            if not (e.source.startswith(prefix) or e.target.startswith(prefix))
        ]

        if len(surviving_nodes) < len(nodes) or len(surviving_edges) < len(edges):
            storage.save(surviving_nodes, surviving_edges)
            logger.info(
                "Purged %d foreign nodes and %d edges for repo %s",
                len(nodes) - len(surviving_nodes),
                len(edges) - len(surviving_edges),
                repo_id,
            )

    # ── Persistence ──────────────────────────────────────────────

    def _load_repos(self) -> list[RepositoryRef]:
        path = self._fed_dir / "repos.jsonl"
        if not path.exists():
            return []
        repos: list[RepositoryRef] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                repos.append(RepositoryRef(**json.loads(line)))
        return repos

    def _save_repos(self) -> None:
        self._fed_dir.mkdir(parents=True, exist_ok=True)
        path = self._fed_dir / "repos.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for ref in self._repos:
                f.write(ref.model_dump_json() + "\n")

    def _load_cross_repo_refs(self) -> list[CrossRepoReference]:
        path = self._fed_dir / "cross_repo_edges.jsonl"
        if not path.exists():
            return []
        refs: list[CrossRepoReference] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                refs.append(CrossRepoReference(**json.loads(line)))
        return refs

    def _save_cross_repo_refs(self, refs: list[CrossRepoReference]) -> None:
        self._fed_dir.mkdir(parents=True, exist_ok=True)
        path = self._fed_dir / "cross_repo_edges.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for ref in refs:
                f.write(ref.model_dump_json() + "\n")
