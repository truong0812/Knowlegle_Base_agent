from __future__ import annotations

import logging
from pathlib import Path

from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.parser.base import ParseResult, SymbolInfo

logger = logging.getLogger(__name__)

RESOLUTION_CONFIDENCE: dict[str, float] = {
    "same_scope": 0.85,
    "same_file": 0.80,
    "direct_import": 0.75,
    "constructor": 0.75,
    "static_call": 0.80,
    "aliased_import": 0.45,
    "dynamic_dispatch": 0.35,
    "unresolved": 0.00,
}

CONFIDENCE_THRESHOLD = 0.50


class GraphBuilder:
    """Builds a symbol graph from parser output."""

    def __init__(self, repo_name: str = "repo") -> None:
        self._repo_name = repo_name
        self._nodes: list[SymbolNode] = []
        self._edges: list[SymbolEdge] = []
        self._node_index: dict[str, SymbolNode] = {}
        self._name_to_ids: dict[str, list[str]] = {}
        self._file_to_ids: dict[str, list[str]] = {}
        self._import_map: dict[str, dict[str, str]] = {}
        self._seen_ids: set[str] = set()

    def build(
        self,
        parse_results: dict[str, ParseResult],
        repo_root: Path | None = None,
    ) -> None:
        """Build graph from all parse results."""
        self._build_import_map(parse_results)

        for file_path, result in parse_results.items():
            self._create_nodes_from_symbols(file_path, result.language, result.symbols)

        self._create_contains_edges(parse_results)
        self._create_imports_edges(parse_results)
        self._resolve_calls_edges(parse_results)
        self._create_type_usage_edges(parse_results)
        self._create_inheritance_edges(parse_results)

    @property
    def nodes(self) -> list[SymbolNode]:
        return self._nodes

    @property
    def edges(self) -> list[SymbolEdge]:
        return self._edges

    # ── Phase 1: Import Map ──────────────────────────────────────

    def _build_import_map(self, parse_results: dict[str, ParseResult]) -> None:
        """Map each file's imported names to their source files."""
        for fp, result in parse_results.items():
            self._import_map[fp] = {}
            for imp in result.imports:
                for name in imp.imported_names:
                    source_file = self._resolve_import_to_file(
                        imp.module_path, name, parse_results,
                    )
                    if source_file:
                        self._import_map[fp][name] = source_file

    def _resolve_import_to_file(
        self,
        module_path: str,
        imported_name: str,
        parse_results: dict[str, ParseResult],
    ) -> str | None:
        """Resolve an import to a file path in the repo."""
        # Strategy 1: Convert dotted module path to file path
        candidates = [
            module_path.replace(".", "/") + ".py",
            module_path.replace(".", "/") + "/__init__.py",
            module_path.replace(".", "/") + ".cs",
            module_path.replace(".", "/") + ".hpp",
            module_path.replace(".", "/") + ".cpp",
        ]
        for candidate in candidates:
            if candidate in parse_results:
                return candidate

        # Strategy 2: Match imported name against file stems
        for fp in parse_results:
            if Path(fp).stem == imported_name:
                return fp

        return None

    # ── Phase 2: Create Nodes ────────────────────────────────────

    def _create_nodes_from_symbols(
        self,
        file_path: str,
        language: Language,
        symbols: list[SymbolInfo],
        parent_name: str | None = None,
    ) -> None:
        """Recursively create SymbolNodes from SymbolInfo tree."""
        for sym in symbols:
            node_id = self._make_unique_id(file_path, sym, parent_name)

            node = SymbolNode(
                id=node_id,
                name=sym.name,
                kind=sym.kind,
                language=language,
                path=file_path,
                line_start=sym.line_start,
                line_end=sym.line_end,
                signature=sym.signature,
                modifiers=sym.modifiers,
                parameters=sym.parameters,
                return_type=sym.return_type,
                docstring=sym.docstring,
            )
            self._nodes.append(node)
            self._node_index[node_id] = node
            self._name_to_ids.setdefault(sym.name, []).append(node_id)
            self._file_to_ids.setdefault(file_path, []).append(node_id)

            if sym.children:
                self._create_nodes_from_symbols(
                    file_path, language, sym.children, parent_name=sym.name,
                )

    def _make_unique_id(
        self, file_path: str, sym: SymbolInfo, parent_name: str | None,
    ) -> str:
        """Build stable path-based node ID with dedup."""
        scope = f"{parent_name}." if parent_name else ""
        param_types = ", ".join(
            p.type.split(".")[-1] if p.type else p.name
            for p in sym.parameters
        )
        base = f"{self._repo_name}/{file_path}::{scope}{sym.name}({param_types})"

        if base not in self._seen_ids:
            self._seen_ids.add(base)
            return base

        # Collision — append line number
        dedup = f"{base}#L{sym.line_start}"
        self._seen_ids.add(dedup)
        return dedup

    # ── Phase 3: CONTAINS Edges ─────────────────────────────────

    def _create_contains_edges(self, parse_results: dict[str, ParseResult]) -> None:
        """Create CONTAINS edges from class nodes to their method children."""
        for fp, result in parse_results.items():
            for sym in result.symbols:
                if not sym.children:
                    continue
                parent_id = self._find_node_id(fp, sym.name, sym.line_start)
                if not parent_id:
                    continue
                for child in sym.children:
                    child_id = self._find_node_id(
                        fp, child.name, child.line_start, parent=sym.name,
                    )
                    if child_id:
                        self._edges.append(SymbolEdge(
                            source=parent_id,
                            target=child_id,
                            kind=EdgeKind.CONTAINS,
                            confidence=1.0,
                            source_type="deterministic",
                            resolution="parent_child",
                        ))

    # ── Phase 4: IMPORTS Edges ──────────────────────────────────

    def _create_imports_edges(self, parse_results: dict[str, ParseResult]) -> None:
        """Create IMPORTS edges from source file symbols to imported file symbols."""
        for fp, parse_results_entry in parse_results.items():
            file_nodes = self._file_to_ids.get(fp, [])
            if not file_nodes:
                continue
            source_node_id = file_nodes[0]  # One edge per file-pair

            for imp in parse_results_entry.imports:
                for imported_name in imp.imported_names:
                    source_file = self._import_map.get(fp, {}).get(imported_name)
                    if not source_file:
                        continue
                    target_ids = self._file_to_ids.get(source_file, [])
                    for tid in target_ids:
                        target_node = self._node_index.get(tid)
                        if target_node and target_node.name == imported_name:
                            self._edges.append(SymbolEdge(
                                source=source_node_id,
                                target=tid,
                                kind=EdgeKind.IMPORTS,
                                confidence=0.95,
                                source_type="deterministic",
                                resolution="direct_import",
                            ))
                            break

    # ── Phase 5: CALLS Edges (Graduated Confidence) ─────────────

    def _resolve_calls_edges(self, parse_results: dict[str, ParseResult]) -> None:
        """Resolve and create CALLS edges with graduated confidence."""
        for fp, result in parse_results.items():
            for call in result.calls:
                caller_id = self._find_enclosing_node(fp, call.line)
                if not caller_id:
                    continue

                effective_resolution = self._upgrade_resolution(fp, call)
                confidence = RESOLUTION_CONFIDENCE.get(effective_resolution, 0.0)
                if confidence < CONFIDENCE_THRESHOLD:
                    continue

                target_id = self._find_callee_target(
                    fp, call, effective_resolution, caller_id,
                )
                if not target_id:
                    continue

                self._edges.append(SymbolEdge(
                    source=caller_id,
                    target=target_id,
                    kind=EdgeKind.CALLS,
                    confidence=confidence,
                    source_type="heuristic",
                    resolution=effective_resolution,
                ))

    def _upgrade_resolution(self, fp: str, call) -> str:
        """Try to upgrade 'unresolved' resolution using import map."""
        if call.resolution_method != "unresolved":
            return call.resolution_method
        import_map = self._import_map.get(fp, {})
        if call.callee_name in import_map:
            return "direct_import"
        return "unresolved"

    def _find_callee_target(
        self,
        fp: str,
        call,
        resolution: str,
        caller_id: str,
    ) -> str | None:
        """Find the target node ID for a call."""
        callee = call.callee_name
        candidate_ids = self._name_to_ids.get(callee, [])

        if resolution == "same_scope":
            parent_class = self._find_parent_class(caller_id)
            if parent_class:
                for edge in self._edges:
                    if edge.source == parent_class and edge.kind == EdgeKind.CONTAINS:
                        target = self._node_index.get(edge.target)
                        if target and target.name == callee:
                            return edge.target

        elif resolution == "same_file":
            for cid in candidate_ids:
                node = self._node_index.get(cid)
                if node and node.path == fp:
                    return cid

        elif resolution == "constructor":
            for cid in candidate_ids:
                node = self._node_index.get(cid)
                if node and node.kind == SymbolKind.CLASS:
                    return cid

        elif resolution == "static_call":
            receiver = call.receiver
            for cid in candidate_ids:
                node = self._node_index.get(cid)
                if node and node.path == fp:
                    return cid
            # Check receiver class children
            receiver_ids = self._name_to_ids.get(receiver, [])
            for rid in receiver_ids:
                rnode = self._node_index.get(rid)
                if rnode and rnode.kind == SymbolKind.CLASS:
                    for edge in self._edges:
                        if edge.source == rid and edge.kind == EdgeKind.CONTAINS:
                            target = self._node_index.get(edge.target)
                            if target and target.name == callee:
                                return edge.target

        elif resolution == "direct_import":
            source_file = self._import_map.get(fp, {}).get(callee)
            if source_file:
                for cid in candidate_ids:
                    node = self._node_index.get(cid)
                    if node and node.path == source_file:
                        return cid

        return None

    # ── Phase 6: USES_TYPE Edges ────────────────────────────────

    def _create_type_usage_edges(self, parse_results: dict[str, ParseResult]) -> None:
        """Create USES_TYPE edges from type annotations."""
        for fp, result in parse_results.items():
            for usage in result.type_usages:
                caller_id = self._find_enclosing_node(fp, usage.line)
                if not caller_id:
                    continue
                target_ids = self._name_to_ids.get(usage.type_name, [])
                for tid in target_ids:
                    self._edges.append(SymbolEdge(
                        source=caller_id,
                        target=tid,
                        kind=EdgeKind.USES_TYPE,
                        confidence=0.80,
                        source_type="heuristic",
                        resolution="type_annotation",
                    ))
                    break

    # ── Phase 7: INHERITS Edges ─────────────────────────────────

    def _create_inheritance_edges(self, parse_results: dict[str, ParseResult]) -> None:
        """Create INHERITS edges from base class declarations."""
        for fp, result in parse_results.items():
            for sym in result.symbols:
                if not sym.bases:
                    continue
                child_id = self._find_node_id(fp, sym.name, sym.line_start)
                if not child_id:
                    continue
                for base_name in sym.bases:
                    base_ids = self._name_to_ids.get(base_name, [])
                    for bid in base_ids:
                        self._edges.append(SymbolEdge(
                            source=child_id,
                            target=bid,
                            kind=EdgeKind.INHERITS,
                            confidence=0.95,
                            source_type="deterministic",
                            resolution="base_class",
                        ))
                        break

    # ── Helpers ──────────────────────────────────────────────────

    def _find_node_id(
        self,
        file_path: str,
        name: str,
        line_start: int,
        parent: str | None = None,
    ) -> str | None:
        """Find node ID by name, file, and optional parent."""
        for nid in self._name_to_ids.get(name, []):
            node = self._node_index.get(nid)
            if node and node.path == file_path and node.line_start == line_start:
                return nid
        # Fallback: match by name and file only
        for nid in self._name_to_ids.get(name, []):
            node = self._node_index.get(nid)
            if node and node.path == file_path:
                return nid
        return None

    def _find_enclosing_node(self, file_path: str, line: int) -> str | None:
        """Find the innermost node whose line range contains the given line."""
        best: str | None = None
        best_range = float("inf")
        for nid in self._file_to_ids.get(file_path, []):
            node = self._node_index.get(nid)
            if not node:
                continue
            if node.line_start <= line <= node.line_end:
                span = node.line_end - node.line_start
                if span < best_range:
                    best = nid
                    best_range = span
        return best

    def _find_parent_class(self, node_id: str) -> str | None:
        """Find the parent class node for a given method node."""
        for edge in self._edges:
            if edge.target == node_id and edge.kind == EdgeKind.CONTAINS:
                return edge.source
        return None
