"""Deterministic learning path generation from graph signals."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path

from kb_agent.learning.models import Citation, LearningLesson, LearningPathDetail, WarningInfo
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode


STARTER_PATH_DEFINITIONS = (
    {
        "id": "architecture-overview",
        "title": "Architecture overview",
        "description": "Understand the repository shape, main modules, and entry points.",
        "minutes": 20,
        "keywords": ("api", "server", "dashboard", "pipeline", "main", "app", "cli", "route"),
        "fallback": "Repository map",
        "objective": "Recognize the main areas of the codebase and how they fit together.",
    },
    {
        "id": "query-and-retrieval",
        "title": "Query and retrieval pipeline",
        "description": "Follow how questions become source-grounded retrieval context.",
        "minutes": 25,
        "keywords": ("query", "retriev", "search", "index", "embed", "rank", "context", "answer"),
        "fallback": "Information flow",
        "objective": "Trace how learner questions are transformed into source-backed context.",
    },
    {
        "id": "knowledge-graph-construction",
        "title": "Knowledge graph construction",
        "description": "Learn how symbols, edges, features, and graph signals are built.",
        "minutes": 30,
        "keywords": ("graph", "node", "edge", "symbol", "feature", "parser", "builder", "storage"),
        "fallback": "Graph model",
        "objective": "Understand how repository structure becomes a navigable knowledge graph.",
    },
)


@dataclass(frozen=True)
class PlannedPaths:
    """Generated path payload plus generation-level warnings."""

    paths: list[LearningPathDetail]
    warnings: list[WarningInfo]


class LearningPathPlanner:
    """Build starter learning paths from graph nodes, edges, and optional hot-path scores."""

    def __init__(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
        hotpath: dict | None = None,
    ) -> None:
        self._nodes = nodes
        self._edges = edges
        self._hotpath = hotpath or {}
        self._node_by_id = {node.id: node for node in nodes}
        self._degree_by_node, self._related_by_node = self._build_graph_indexes()
        self._warnings: list[WarningInfo] = []
        self._cycle_edges = self._find_cycle_edges()

    def generate(self) -> PlannedPaths:
        """Return at least three deterministic starter paths when graph data exists."""
        if not self._nodes:
            return PlannedPaths(paths=[], warnings=[])

        paths = []
        used_ids: set[str] = set()
        for definition in STARTER_PATH_DEFINITIONS:
            candidates = self._rank_candidates(definition["keywords"], used_ids)
            if not candidates:
                candidates = self._rank_candidates((), used_ids)
            selected = candidates[:3]
            used_ids.update(node.id for node in selected)
            paths.append(self._build_path(definition, selected))

        warnings = [*self._warnings]
        if self._cycle_edges:
            warnings.append(
                WarningInfo(
                    code="circular_dependency_detected",
                    message="Circular graph relationships were detected and ordered with graph signal scoring.",
                )
            )
        return PlannedPaths(paths=paths, warnings=warnings)

    def _build_path(self, definition: dict, nodes: list[SymbolNode]) -> LearningPathDetail:
        lessons: list[LearningLesson] = []
        for index, node in enumerate(nodes):
            lesson_id = f"lesson-{index + 1}"
            next_lesson_id = f"lesson-{index + 2}" if index + 1 < len(nodes) else None
            lessons.append(
                LearningLesson(
                    id=lesson_id,
                    title=self._lesson_title(index, node, definition["fallback"]),
                    summary=f"Learn {node.name} in {node.path}.",
                    explanation=self._lesson_explanation(node),
                    key_concepts=self._key_concepts(node),
                    related_topics=self._related_topics(node.id),
                    citations=[
                        Citation(
                            label=node.name,
                            path=node.path,
                            line_start=node.line_start,
                            line_end=node.line_end,
                            node_id=node.id,
                        )
                    ],
                    next_lesson_id=next_lesson_id,
                )
            )

        while len(lessons) < 3:
            index = len(lessons)
            lesson_id = f"lesson-{index + 1}"
            next_lesson_id = f"lesson-{index + 2}" if index < 2 else None
            lessons.append(
                LearningLesson(
                    id=lesson_id,
                    title=f"{definition['fallback']} step {index + 1}",
                    summary="Use the topic explorer to inspect the next available source-backed concept.",
                    explanation=(
                        "The graph does not have enough high-confidence symbols for this slot yet, "
                        "so this lesson keeps the path usable while pointing back to source topics."
                    ),
                    key_concepts=["topic", "source", "graph"],
                    next_lesson_id=next_lesson_id,
                )
            )

        return LearningPathDetail(
            id=definition["id"],
            title=definition["title"],
            description=definition["description"],
            estimated_minutes=definition["minutes"],
            lesson_count=len(lessons),
            prerequisites=[] if definition["id"] == "architecture-overview" else ["architecture-overview"],
            objectives=[
                definition["objective"],
                "Open source citations for each lesson before moving on.",
                "Use related topics to branch into deeper graph context.",
            ],
            lessons=lessons,
            warnings=[*self._warnings],
        )

    def _rank_candidates(self, keywords: tuple[str, ...], used_ids: set[str]) -> list[SymbolNode]:
        nodes = [node for node in self._nodes if node.id not in used_ids]
        if not nodes:
            nodes = list(self._nodes)
        return sorted(
            nodes,
            key=lambda node: (
                -self._node_score(node, keywords),
                node.path,
                node.line_start,
                node.name,
            ),
        )

    def _node_score(self, node: SymbolNode, keywords: tuple[str, ...]) -> float:
        text = f"{node.name} {node.path} {node.signature or ''} {node.docstring or ''}".lower()
        keyword_score = sum(1 for keyword in keywords if keyword in text)
        edge_score = self._degree(node.id) * 0.1
        hot = self._hotpath.get(node.id)
        hotness = getattr(hot, "hotness", 0.0)
        kind_score = 0.2 if node.kind.value in {"class", "function", "method", "module"} else 0.0
        return keyword_score + edge_score + hotness + kind_score

    def _degree(self, node_id: str) -> int:
        return self._degree_by_node.get(node_id, 0)

    def _related_topics(self, node_id: str) -> list[str]:
        return self._related_by_node.get(node_id, [])[:5]

    def _key_concepts(self, node: SymbolNode) -> list[str]:
        path_parts = [part for part in Path(node.path).parts[:2] if part]
        concepts = [node.kind.value, *path_parts, node.name]
        seen: set[str] = set()
        return [item for item in concepts if not (item in seen or seen.add(item))][:5]

    def _lesson_explanation(self, node: SymbolNode) -> str:
        signature = f" Its signature is `{node.signature}`." if node.signature else ""
        doc = f" The docstring says: {node.docstring}" if node.docstring else ""
        return (
            f"Start with `{node.name}` because it is a {node.kind.value} in `{node.path}`. "
            f"Inspect the cited source range to connect the concept to real code.{signature}{doc}"
        )

    def _lesson_title(self, index: int, node: SymbolNode, fallback: str) -> str:
        if index == 0:
            return f"Start with {node.name}"
        if index == 1:
            return f"Connect {node.name}"
        return f"Practice with {node.name}" if node.name else f"{fallback} step {index + 1}"

    def _build_graph_indexes(self) -> tuple[dict[str, int], dict[str, list[str]]]:
        degree_by_node: dict[str, int] = {}
        related_by_node: dict[str, list[str]] = {}
        for edge in self._edges:
            source_exists = edge.source in self._node_by_id
            target_exists = edge.target in self._node_by_id
            if source_exists:
                degree_by_node[edge.source] = degree_by_node.get(edge.source, 0) + 1
            if target_exists:
                degree_by_node[edge.target] = degree_by_node.get(edge.target, 0) + 1
            if source_exists and target_exists:
                related_by_node.setdefault(edge.source, []).append(edge.target)
                related_by_node.setdefault(edge.target, []).append(edge.source)
        return degree_by_node, related_by_node

    def _find_cycle_edges(self) -> set[tuple[str, str]]:
        adjacency: dict[str, list[str]] = {}
        for edge in self._edges:
            if edge.kind in {EdgeKind.CALLS, EdgeKind.IMPORTS, EdgeKind.USES_TYPE, EdgeKind.INHERITS}:
                adjacency.setdefault(edge.source, []).append(edge.target)

        cycle_edges: set[tuple[str, str]] = set()
        visiting: set[str] = set()
        visited: set[str] = set()

        for node_id in sorted(adjacency):
            if node_id in visited:
                continue
            stack: list[tuple[str, int]] = [(node_id, 0)]
            path: list[str] = []
            path_index: dict[str, int] = {}

            while stack:
                current, next_index = stack[-1]
                if next_index == 0:
                    if current in visited:
                        stack.pop()
                        continue
                    visiting.add(current)
                    path_index[current] = len(path)
                    path.append(current)

                neighbors = adjacency.get(current, [])
                if next_index >= len(neighbors):
                    stack.pop()
                    visiting.discard(current)
                    visited.add(current)
                    if path and path[-1] == current:
                        path.pop()
                    path_index.pop(current, None)
                    continue

                target = neighbors[next_index]
                stack[-1] = (current, next_index + 1)
                if target in visiting:
                    start = path_index.get(target, 0)
                    cycle = path[start:] + [target]
                    for source, cycle_target in zip(cycle, cycle[1:], strict=False):
                        cycle_edges.add((source, cycle_target))
                    continue
                if target not in visited:
                    stack.append((target, 0))
        return cycle_edges


def default_path_planner_factory(
    nodes: list[SymbolNode],
    edges: list[SymbolEdge],
    hotpath: dict | None = None,
) -> LearningPathPlanner:
    """Create the default deterministic learning path planner."""
    return LearningPathPlanner(nodes, edges, hotpath)


def paths_cache_key(manifest: dict | None, node_count: int, edge_count: int) -> str:
    """Return a stable cache key for generated paths."""
    raw = {
        "source_repo": manifest.get("source_repo") if manifest else None,
        "created_at": manifest.get("created_at") if manifest else None,
        "version": manifest.get("version") if manifest else None,
        "node_count": node_count,
        "edge_count": edge_count,
    }
    return sha1(repr(sorted(raw.items())).encode("utf-8")).hexdigest()
