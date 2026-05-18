"""Post-build symbol resolver that improves edge confidence."""
from __future__ import annotations

import logging

from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.parser.base import normalize_decorator

logger = logging.getLogger(__name__)

DECORATOR_CONFIDENCE_RESOLUTIONS = {
    "aliased_import",
    "dynamic_dispatch",
    "inherited_scope",
    "type_inferred",
}

class EnhancedResolver:
    """Post-build resolver for inherited calls and decorator confidence rules."""

    def __init__(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
        node_index: dict[str, SymbolNode],
        name_to_ids: dict[str, list[str]],
        class_children: dict[str, dict[str, str]],
        child_to_parent: dict[str, str],
    ) -> None:
        self._nodes = nodes
        self._edges = edges
        self._node_index = node_index
        self._name_to_ids = name_to_ids
        self._class_children = class_children
        self._child_to_parent = child_to_parent
        self._inheritance_map = self._build_inheritance_map()

    def resolve_all(self) -> list[SymbolEdge]:
        """Run enhanced resolution passes and return newly resolved edges."""
        new_edges = self.resolve_inherited_calls()
        self.resolve_decorator_scopes()
        return new_edges

    def resolve_inherited_calls(self) -> list[SymbolEdge]:
        """Resolve same-scope calls that should point to inherited methods."""
        new_edges: list[SymbolEdge] = []
        calls_to_remove: list[int] = []

        for i, edge in enumerate(self._edges):
            if edge.kind != EdgeKind.CALLS or edge.resolution != "same_scope":
                continue

            callee_name = self._extract_callee_name(edge.target)
            if not callee_name:
                continue

            parent_class = self._find_parent_class(edge.source)
            if not parent_class:
                continue

            if self._class_children.get(parent_class, {}).get(callee_name):
                continue

            resolved_target = self._resolve_inherited_method(parent_class, callee_name)
            if resolved_target and resolved_target != edge.target:
                calls_to_remove.append(i)
                new_edges.append(SymbolEdge(
                    source=edge.source,
                    target=resolved_target,
                    kind=EdgeKind.CALLS,
                    confidence=0.80,
                    source_type="heuristic",
                    resolution="inherited_scope",
                ))

        for i in sorted(calls_to_remove, reverse=True):
            self._edges.pop(i)

        if new_edges:
            logger.debug(
                "Inherited resolution: %d calls resolved via inheritance chain",
                len(new_edges),
            )
        return new_edges

    def resolve_decorator_scopes(self) -> None:
        """Adjust confidence for decorator-annotated methods in-place."""
        adjusted = 0
        for edge in self._edges:
            if edge.kind != EdgeKind.CALLS:
                continue

            target_node = self._node_index.get(edge.target)
            if not target_node:
                continue

            normalized_mods = {normalize_decorator(m) for m in target_node.modifiers}
            if (
                "injected" in normalized_mods
                and edge.resolution in DECORATOR_CONFIDENCE_RESOLUTIONS
                and edge.confidence > 0.50
            ):
                edge.confidence = 0.50
                adjusted += 1

        if adjusted:
            logger.debug("Decorator scope: adjusted %d edges", adjusted)

    def _build_inheritance_map(self) -> dict[str, list[str]]:
        inh_map: dict[str, list[str]] = {}
        for edge in self._edges:
            if edge.kind == EdgeKind.INHERITS:
                inh_map.setdefault(edge.source, []).append(edge.target)
        return inh_map

    def _find_parent_class(self, node_id: str) -> str | None:
        return self._child_to_parent.get(node_id)

    def _resolve_inherited_method(
        self, class_id: str, method_name: str,
    ) -> str | None:
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

            for ancestor_id in self._inheritance_map.get(current, []):
                if ancestor_id not in visited:
                    queue.append(ancestor_id)
        return None

    def _extract_callee_name(self, target_id: str) -> str | None:
        node = self._node_index.get(target_id)
        if node:
            return node.name
        if "::" in target_id:
            after_scope = target_id.split("::")[-1]
            return after_scope.split(".")[-1].split("(")[0]
        return None
