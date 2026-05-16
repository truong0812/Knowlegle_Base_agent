from __future__ import annotations

import logging
from pathlib import Path

from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.parser.base import AssignmentInfo, ParseResult, SymbolInfo

logger = logging.getLogger(__name__)

RESOLUTION_CONFIDENCE: dict[str, float] = {
    "same_scope": 0.85,
    "same_file": 0.80,
    "direct_import": 0.75,
    "constructor": 0.75,
    "static_call": 0.80,
    "aliased_import": 0.70,
    "inherited_scope": 0.80,
    "type_inferred": 0.65,
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
        # Core indexes
        self._node_index: dict[str, SymbolNode] = {}
        self._name_to_ids: dict[str, list[str]] = {}
        self._file_to_ids: dict[str, list[str]] = {}
        self._import_map: dict[str, dict[str, str]] = {}
        self._import_aliases: dict[str, dict[str, str]] = {}
        self._seen_ids: set[str] = set()
        # Optimization indexes (built after nodes phase)
        self._file_symbol_map: dict[str, dict[str, str]] = {}
        self._child_to_parent: dict[str, str] = {}
        self._class_children: dict[str, dict[str, str]] = {}
        self._sorted_file_nodes: dict[str, list[tuple[int, int, str]]] = {}

    def build(
        self,
        parse_results: dict[str, ParseResult],
        repo_root: Path | None = None,
    ) -> None:
        """Build graph from all parse results."""
        self._build_import_map(parse_results)

        for file_path, result in parse_results.items():
            self._create_nodes_from_symbols(file_path, result.language, result.symbols)

        self._build_optimization_indexes()

        self._create_contains_edges(parse_results)
        self._create_imports_edges(parse_results)
        self._create_inheritance_edges(parse_results)
        self._resolve_calls_edges(parse_results)
        self._create_type_usage_edges(parse_results)

        self._enhanced_resolve(parse_results)
        self._propagate_confidences()

    @property
    def nodes(self) -> list[SymbolNode]:
        return self._nodes

    @property
    def edges(self) -> list[SymbolEdge]:
        return self._edges

    # ── Optimization Indexes ─────────────────────────────────────

    def _build_optimization_indexes(self) -> None:
        """Pre-build lookup indexes for O(1) access patterns."""
        # file_symbol_map: {file_path: {symbol_name: node_id}}
        for nid, node in self._node_index.items():
            self._file_symbol_map.setdefault(node.path, {})[node.name] = nid

        # sorted_file_nodes: {file_path: [(line_start, line_end, node_id)]} sorted by line_start
        for fp, ids in self._file_to_ids.items():
            entries = []
            for nid in ids:
                node = self._node_index.get(nid)
                if node:
                    entries.append((node.line_start, node.line_end, nid))
            entries.sort(key=lambda x: x[0])
            self._sorted_file_nodes[fp] = entries

    def _register_contains_index(self, parent_id: str, child_id: str, child_name: str) -> None:
        """Update indexes when a CONTAINS edge is created."""
        self._child_to_parent[child_id] = parent_id
        self._class_children.setdefault(parent_id, {})[child_name] = child_id

    # ── Phase 8: Enhanced Resolution ─────────────────────────────

    def _enhanced_resolve(self, parse_results: dict[str, ParseResult]) -> None:
        """Post-build enhanced symbol resolution."""
        from kb_agent.graph.resolver import EnhancedResolver

        resolver = EnhancedResolver(
            nodes=self._nodes,
            edges=self._edges,
            node_index=self._node_index,
            name_to_ids=self._name_to_ids,
            class_children=self._class_children,
            child_to_parent=self._child_to_parent,
        )
        new_edges = resolver.resolve_all()
        self._edges.extend(new_edges)

    def _propagate_confidences(self) -> None:
        """Compute and store node confidence from edge density."""
        from kb_agent.graph.confidence import ConfidencePropagator

        propagator = ConfidencePropagator(self._nodes, self._edges)
        node_confs = propagator.compute_node_confidences()
        for nid, nc in node_confs.items():
            node = self._node_index.get(nid)
            if node:
                node.confidence = nc.propagated_confidence

    # ── Phase 1: Import Map ──────────────────────────────────────

    def _build_import_map(self, parse_results: dict[str, ParseResult]) -> None:
        """Map each file's imported names to their source files."""
        for fp, result in parse_results.items():
            self._import_map[fp] = {}
            self._import_aliases[fp] = {}
            for imp in result.imports:
                for name in imp.imported_names:
                    source_file = self._resolve_import_to_file(
                        imp.module_path, name, parse_results,
                    )
                    if source_file:
                        self._import_map[fp][name] = source_file
                        self._import_aliases[fp][name] = name
                for local_name, imported_name in imp.aliases.items():
                    source_file = self._resolve_import_to_file(
                        imp.module_path, imported_name, parse_results,
                    )
                    if source_file:
                        self._import_map[fp][local_name] = source_file
                        self._import_aliases[fp][local_name] = imported_name

    def _resolve_import_to_file(
        self,
        module_path: str,
        imported_name: str,
        parse_results: dict[str, ParseResult],
    ) -> str | None:
        """Resolve an import to a file path in the repo."""
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
                        self._register_contains_index(parent_id, child_id, child.name)

    # ── Phase 4: IMPORTS Edges ──────────────────────────────────

    def _create_imports_edges(self, parse_results: dict[str, ParseResult]) -> None:
        """Create IMPORTS edges using file_symbol_map for O(1) lookup."""
        for fp, parse_results_entry in parse_results.items():
            file_nodes = self._file_to_ids.get(fp, [])
            if not file_nodes:
                continue
            source_node_id = file_nodes[0]

            for imp in parse_results_entry.imports:
                for imported_name in imp.imported_names:
                    source_file = self._import_map.get(fp, {}).get(imported_name)
                    if not source_file:
                        continue
                    target_id = self._file_symbol_map.get(source_file, {}).get(imported_name)
                    if target_id:
                        self._edges.append(SymbolEdge(
                            source=source_node_id,
                            target=target_id,
                            kind=EdgeKind.IMPORTS,
                            confidence=0.95,
                            source_type="deterministic",
                            resolution="direct_import",
                        ))

    # ── Phase 5: CALLS Edges (Graduated Confidence) ─────────────

    def _resolve_calls_edges(self, parse_results: dict[str, ParseResult]) -> None:
        """Resolve and create CALLS edges with graduated confidence."""
        # Build assignment map for type inference.
        assignment_map: dict[str, list[AssignmentInfo]] = {}
        for fp, result in parse_results.items():
            assignment_map[fp] = result.assignments

        for fp, result in parse_results.items():
            for call in result.calls:
                caller_id = self._find_enclosing_node(fp, call.line)
                if not caller_id:
                    continue

                effective_resolution = self._upgrade_resolution(fp, call)
                confidence = RESOLUTION_CONFIDENCE.get(effective_resolution, 0.0)

                # If below threshold, try type inference before dropping
                if confidence < CONFIDENCE_THRESHOLD:
                    target_id = self._try_type_inference(
                        caller_id, call, fp, assignment_map,
                    )
                    if target_id:
                        self._edges.append(SymbolEdge(
                            source=caller_id,
                            target=target_id,
                            kind=EdgeKind.CALLS,
                            confidence=RESOLUTION_CONFIDENCE["type_inferred"],
                            source_type="heuristic",
                            resolution="type_inferred",
                        ))
                    continue

                target_id = self._find_callee_target(
                    fp, call, effective_resolution, caller_id,
                )
                if not target_id:
                    continue

                # Check if same_scope was resolved via inheritance chain
                if effective_resolution == "same_scope":
                    parent_class = self._child_to_parent.get(caller_id)
                    if parent_class and target_id not in self._class_children.get(parent_class, {}).values():
                        effective_resolution = "inherited_scope"
                        confidence = RESOLUTION_CONFIDENCE["inherited_scope"]

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
            original_name = self._import_aliases.get(fp, {}).get(call.callee_name)
            if original_name and original_name != call.callee_name:
                return "aliased_import"
            return "direct_import"
        return "unresolved"

    def _find_callee_target(
        self,
        fp: str,
        call,
        resolution: str,
        caller_id: str,
    ) -> str | None:
        """Find the target node ID for a call using pre-built indexes."""
        callee = call.callee_name

        if resolution == "same_scope":
            parent_class = self._find_parent_class(caller_id)
            if parent_class:
                target = self._class_children.get(parent_class, {}).get(callee)
                if target:
                    return target
                # Fallback: walk inheritance chain
                return self._resolve_inherited_method(parent_class, callee)

        elif resolution == "same_file":
            return self._file_symbol_map.get(fp, {}).get(callee)

        elif resolution == "constructor":
            for cid in self._name_to_ids.get(callee, []):
                node = self._node_index.get(cid)
                if node and node.kind == SymbolKind.CLASS:
                    return cid

        elif resolution == "static_call":
            receiver = call.receiver
            receiver_ids = self._name_to_ids.get(receiver, [])
            for rid in receiver_ids:
                rnode = self._node_index.get(rid)
                if rnode and rnode.kind == SymbolKind.CLASS:
                    return self._class_children.get(rid, {}).get(callee)

        elif resolution in ("direct_import", "aliased_import"):
            source_file = self._import_map.get(fp, {}).get(callee)
            if source_file:
                imported_name = self._import_aliases.get(fp, {}).get(callee, callee)
                return self._file_symbol_map.get(source_file, {}).get(imported_name)

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

    def _try_type_inference(
        self,
        caller_id: str,
        call,
        file_path: str,
        assignment_map: dict[str, list[AssignmentInfo]],
    ) -> str | None:
        """Try to resolve a dynamic_dispatch call via type inference.

        Flow: receiver → assignment_map → callee_name → return_type → class → method
        """
        receiver = getattr(call, "receiver", None)
        if not receiver:
            return None
        callee_name = call.callee_name

        # Look up the nearest previous assignment in the same enclosing node:
        # svc = get_service(); svc.login()
        candidates = [
            asgn for asgn in assignment_map.get(file_path, [])
            if asgn.variable_name == receiver
            and asgn.line <= call.line
            and self._find_enclosing_node(file_path, asgn.line) == caller_id
        ]
        if not candidates:
            return None
        assigned_callee = max(candidates, key=lambda asgn: asgn.line).callee_name

        # Find that function's return type
        ret_type: str | None = None
        for nid in self._name_to_ids.get(assigned_callee, []):
            node = self._node_index.get(nid)
            if node and node.return_type:
                ret_type = node.return_type
                break
        if not ret_type:
            return None

        # Resolve return type to a class node
        class_id = self._resolve_type_to_class_id(ret_type)
        if not class_id:
            return None

        # Find the method on that class
        return self._class_children.get(class_id, {}).get(callee_name)

    def _resolve_type_to_class_id(self, type_name: str) -> str | None:
        """Resolve a type name string to a class node ID."""
        clean = type_name.strip("[]").split("[")[-1].strip("]").strip()
        clean = clean.split(".")[-1]
        for nid in self._name_to_ids.get(clean, []):
            node = self._node_index.get(nid)
            if node and node.kind == SymbolKind.CLASS:
                return nid
        return None

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
        for nid in self._name_to_ids.get(name, []):
            node = self._node_index.get(nid)
            if node and node.path == file_path:
                return nid
        return None

    def _find_enclosing_node(self, file_path: str, line: int) -> str | None:
        """Find the innermost node whose line range contains the given line.

        Uses binary search on pre-sorted nodes for O(log N) lookup.
        """
        entries = self._sorted_file_nodes.get(file_path)
        if not entries:
            return None

        best: str | None = None
        best_range = float("inf")

        # Find the first node that starts at or before the target line
        lo, hi = 0, len(entries)
        while lo < hi:
            mid = (lo + hi) // 2
            if entries[mid][0] <= line:
                lo = mid + 1
            else:
                hi = mid

        # Check candidates near the found position (going backwards)
        for i in range(lo - 1, -1, -1):
            start, end, nid = entries[i]
            if start > line:
                continue
            if start <= line <= end:
                span = end - start
                if span < best_range:
                    best = nid
                    best_range = span
            elif end < line:
                break

        return best

    def _find_parent_class(self, node_id: str) -> str | None:
        """Find the parent class node for a given method node. O(1) via index."""
        return self._child_to_parent.get(node_id)

    def _resolve_inherited_method(self, class_id: str, method_name: str) -> str | None:
        """Walk inheritance edges to find a method in ancestor classes."""
        visited: set[str] = set()
        queue = [class_id]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            method_id = self._class_children.get(current, {}).get(method_name)
            if method_id:
                return method_id
            # Follow INHERITS edges to ancestors
            for edge in self._edges:
                if edge.kind == EdgeKind.INHERITS and edge.source == current:
                    if edge.target not in visited:
                        queue.append(edge.target)
        return None
