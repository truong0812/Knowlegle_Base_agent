"""Learning path catalog and persistence helpers."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import orjson

from kb_agent.learning.models import LearningPathDetail, WarningInfo
from kb_agent.learning.planner import default_path_planner_factory, paths_cache_key
from kb_agent.models.graph import SymbolEdge, SymbolNode


logger = logging.getLogger(__name__)

GraphCache = tuple[list[SymbolNode], list[SymbolEdge]]


class PathPlanningResult(Protocol):
    """Planner result shape consumed by the path catalog."""

    paths: list[LearningPathDetail]
    warnings: list[WarningInfo]


class PathPlanner(Protocol):
    """Interface required for learning path generation."""

    def generate(self) -> PathPlanningResult:
        """Generate path details and warnings."""
        ...


PathPlannerFactory = Callable[[list[SymbolNode], list[SymbolEdge], dict], PathPlanner]


class LearningPathRepository:
    """Persist and retrieve generated learning path details."""

    def __init__(self, learning_dir: Path) -> None:
        self._learning_dir = learning_dir
        self._cache_path = learning_dir / "paths.json"

    def load(self, cache_key: str) -> list[LearningPathDetail]:
        """Load paths only when the cache key matches the current KB graph."""
        if not self._cache_path.exists():
            return []
        try:
            payload = orjson.loads(self._cache_path.read_bytes())
        except (OSError, orjson.JSONDecodeError):
            logger.warning("Invalid or unreadable learning paths cache at %s; regenerating.", self._cache_path)
            return []
        if not isinstance(payload, dict):
            logger.warning("Learning paths cache at %s is not a JSON object; regenerating.", self._cache_path)
            return []
        if payload.get("cache_key") != cache_key:
            return []

        try:
            return [
                LearningPathDetail.model_validate(path)
                for path in payload.get("paths", [])
                if isinstance(path, dict)
            ]
        except Exception:
            logger.warning("Learning paths cache at %s failed validation; regenerating.", self._cache_path)
            return []

    def store(self, cache_key: str, generated_at: str, paths: list[LearningPathDetail]) -> None:
        """Persist generated paths and the cache key they belong to."""
        payload = {
            "cache_key": cache_key,
            "generated_at": generated_at,
            "paths": [path.model_dump() for path in paths],
        }
        self._learning_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))


class LearningPathCatalog:
    """Coordinate path retrieval, generation, and persistence."""

    def __init__(
        self,
        repository: LearningPathRepository,
        planner_factory: PathPlannerFactory | None = None,
    ) -> None:
        self._repository = repository
        self._planner_factory = planner_factory or default_path_planner_factory
        self._paths_cache: list[LearningPathDetail] | None = None
        self._path_index_cache: dict[str, LearningPathDetail] | None = None

    def paths(
        self,
        *,
        graph: GraphCache | None,
        manifest: dict | None,
        hotpath_loader: Callable[[], dict],
        generated_at: str,
        non_blocking: bool = False,
    ) -> list[LearningPathDetail]:
        """Return cached paths or generate and persist them for the current graph."""
        if self._paths_cache is not None:
            return self._paths_cache
        if graph is None:
            self._set_memory_cache([])
            return []

        cache_key = self._cache_key(manifest, graph)
        cached = self._repository.load(cache_key)
        if cached:
            self._set_memory_cache(cached)
            return cached
        if non_blocking:
            return []

        generated = self._generate_paths(graph, hotpath_loader())
        self._set_memory_cache(generated)
        if generated:
            self._repository.store(cache_key, generated_at, generated)
        return generated

    def path_index(
        self,
        *,
        graph: GraphCache | None,
        manifest: dict | None,
        hotpath_loader: Callable[[], dict],
        generated_at: str,
    ) -> dict[str, LearningPathDetail]:
        """Return an id-indexed path map for O(1) lookup."""
        if self._path_index_cache is not None:
            return self._path_index_cache
        paths = self.paths(
            graph=graph,
            manifest=manifest,
            hotpath_loader=hotpath_loader,
            generated_at=generated_at,
        )
        self._path_index_cache = self._build_path_index(paths)
        return self._path_index_cache

    def _generate_paths(self, graph: GraphCache, hotpath: dict) -> list[LearningPathDetail]:
        nodes, edges = graph
        try:
            planned = self._planner_factory(nodes, edges, hotpath).generate()
        except Exception:
            logger.exception("Learning path planner failed.")
            return []
        return [
            path.model_copy(update={"warnings": [*path.warnings, *planned.warnings]})
            for path in planned.paths
        ]

    def _set_memory_cache(self, paths: list[LearningPathDetail]) -> None:
        self._paths_cache = paths
        self._path_index_cache = self._build_path_index(paths)

    def _build_path_index(self, paths: list[LearningPathDetail]) -> dict[str, LearningPathDetail]:
        return {path.id: path for path in paths}

    def _cache_key(self, manifest: dict | None, graph: GraphCache) -> str:
        nodes, edges = graph
        return paths_cache_key(manifest, len(nodes), len(edges))
