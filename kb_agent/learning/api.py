"""Learning platform API helpers."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
import logging
from pathlib import Path

import orjson

from kb_agent.graph.storage import GraphStorage, ReadOnlyStorage
from kb_agent.learning.explainer import PROMPT_VERSION as TOPIC_PROMPT_VERSION
from kb_agent.learning.explainer import TopicExplainer, cache_payload
from kb_agent.learning.models import (
    DashboardResponse,
    KbStatus,
    LearningPathDetail,
    LearningPathSummary,
    NextAction,
    PathProgress,
    ProgressEvent,
    ProgressSummary,
    ProjectSummary,
    Recommendation,
    TopicPage,
    TopicProgress,
    TopicSearchResult,
    TutorRequest,
    TutorResponse,
    UserProgress,
    WarningInfo,
)
from kb_agent.learning.planner import LearningPathPlanner, paths_cache_key
from kb_agent.learning.tutor import Tutor, default_tutor_factory
from kb_agent.models.graph import SymbolEdge, SymbolNode


logger = logging.getLogger(__name__)

GraphCache = tuple[list[SymbolNode], list[SymbolEdge]]
TutorFactory = Callable[..., Tutor]
_UNSET = object()


class LearningApi:
    """Builds stable learning API contract responses.

    Phase 1 intentionally returns deterministic placeholder content. Later phases
    can replace each method with generated paths, topic explanations, and tutor
    synthesis without changing endpoint shapes.
    """

    def __init__(
        self,
        kb_dir: Path,
        storage: ReadOnlyStorage | None = None,
        tutor_factory: TutorFactory | None = None,
    ):
        self.kb_dir = kb_dir.resolve()
        self.graph_dir = self.kb_dir / "graph"
        self.entries_dir = self.kb_dir / "entries"
        self.learning_dir = self.kb_dir / "learning"
        self.storage = storage or GraphStorage(self.graph_dir)
        self._tutor_factory = tutor_factory or default_tutor_factory
        self._manifest_cache: dict | None | object = _UNSET
        self._graph_cache: GraphCache | None | object = _UNSET
        self._kb_status_cache: KbStatus | None = None
        self._features_cache: list | None = None
        self._progress_cache: UserProgress | None = None
        self._tutor_cache: Tutor | None = None
        self._topic_explainer_cache: TopicExplainer | None = None
        self._topic_cache: dict[str, dict] | None = None
        self._paths_cache: list[LearningPathDetail] | None = None
        self._path_index_cache: dict[str, LearningPathDetail] | None = None

    def dashboard(self) -> DashboardResponse:
        manifest = self._load_manifest()
        status = self.kb_status(manifest)
        paths = self.paths()
        topics = self._recommended_topics()
        progress = self.progress_summary()
        next_action = self._next_action(paths, status)

        return DashboardResponse(
            summary=self.project_summary(manifest),
            kb_status=status,
            progress=progress,
            recommended_paths=paths,
            recommended_topics=topics,
            important_features=self._important_features(),
            recent_activity=[],
            suggested_next_action=next_action,
        )

    def kb_status(self, manifest: dict | None = None) -> KbStatus:
        if manifest is None and self._kb_status_cache is not None:
            return self._kb_status_cache
        warnings: list[WarningInfo] = []
        if manifest is None:
            manifest = self._load_manifest()
        if manifest is None:
            status = KbStatus(
                available=False,
                warnings=[
                    WarningInfo(
                        code="missing_kb",
                        message="Knowledge base not found. Run analyze first.",
                    )
                ],
            )
            self._kb_status_cache = status
            return status

        node_count = 0
        edge_count = 0
        graph = self._graph()
        if graph is not None:
            nodes, edges = graph
            node_count = len(nodes)
            edge_count = len(edges)
        else:
            warnings.append(
                WarningInfo(
                    code="missing_graph",
                    message="Graph files are missing; learning responses use manifest data only.",
                )
            )

        entry_count = self._entry_count(manifest)
        status = KbStatus(
            available=True,
            node_count=node_count,
            edge_count=edge_count,
            entry_count=entry_count,
            warnings=warnings,
        )
        self._kb_status_cache = status
        return status

    def project_summary(self, manifest: dict | None = None) -> ProjectSummary:
        if manifest is None:
            manifest = self._load_manifest()
        source_repo = manifest.get("source_repo") if manifest else None
        project_name = Path(source_repo).name if source_repo else "Knowledge Base"
        return ProjectSummary(
            project_name=project_name,
            description=self._arch_summary() or "Learning workspace for this knowledge base.",
            source_repo=source_repo,
            created_at=manifest.get("created_at") if manifest else None,
        )

    def paths(self, *, non_blocking: bool = False) -> list[LearningPathSummary]:
        return [
            self._summary_from_detail(self._apply_detail_progress(path))
            for path in self._learning_paths(non_blocking=non_blocking)
        ]

    def path_detail(self, path_id: str) -> LearningPathDetail | None:
        detail = self._learning_path_index().get(path_id)
        if detail is None:
            return None
        return self._apply_detail_progress(detail)

    def complete_lesson(self, path_id: str, lesson_id: str) -> dict:
        detail = self.path_detail(path_id)
        if detail is None:
            return {
                "path_id": path_id,
                "lesson_id": lesson_id,
                "completed": False,
                "progress": PathProgress().model_dump(),
                "next_action": NextAction(type="start_path", label="Choose a learning path", target_id=None).model_dump(),
            }

        lesson_ids = [lesson.id for lesson in detail.lessons]
        completed = lesson_id in lesson_ids
        next_lesson_id = None
        if completed:
            current_index = lesson_ids.index(lesson_id)
            if current_index + 1 < len(lesson_ids):
                next_lesson_id = lesson_ids[current_index + 1]
            self.accept_progress_event(
                ProgressEvent(
                    event_type="path_started",
                    context={
                        "page": "path",
                        "path_id": path_id,
                        "lesson_id": lesson_id,
                    },
                )
            )
            self.accept_progress_event(
                ProgressEvent(
                    event_type="lesson_completed",
                    context={
                        "page": "path",
                        "path_id": path_id,
                        "lesson_id": lesson_id,
                    },
                )
            )
            detail = self.path_detail(path_id) or detail
        return {
            "path_id": path_id,
            "lesson_id": lesson_id,
            "completed": completed,
            "progress": detail.progress.model_dump(),
            "next_action": NextAction(
                type="continue_path" if next_lesson_id else "open_topic",
                label="Continue to next lesson" if next_lesson_id else "Open related topics",
                target_id=next_lesson_id,
            ).model_dump(),
        }

    def topic(self, topic_id: str) -> TopicPage:
        explainer = self._topic_explainer()
        try:
            node = explainer.resolve(topic_id)
        except Exception as exc:
            logger.exception("Topic resolution failed for %s.", topic_id)
            return self._topic_error_page(topic_id, exc)

        if node is not None:
            self.accept_progress_event(
                ProgressEvent(
                    event_type="topic_viewed",
                    context={"page": "topic", "topic_id": node.id},
                )
            )
            progress = self.progress()
            topic_progress = next(
                (item for item in progress.viewed_topics if item.get("topic_id") == node.id),
                {},
            )
            cache = self._load_topic_cache()
            cache_key = self._topic_cache_key(node.id)
            page = self._safe_explain_topic(
                explainer,
                topic_id,
                progress=TopicProgress(
                    viewed=True,
                    last_viewed_at=topic_progress.get("viewed_at"),
                ),
                cached=cache.get(cache_key) or cache.get(node.id),
            )
            if cache_key not in cache and not self._topic_has_error(page):
                self._store_topic_cache(page)
            return page

        return self._safe_explain_topic(explainer, topic_id)

    def search_topics(self, query: str) -> dict:
        results = self._topic_explainer().search(query)
        return {"query": query, "results": [item.model_dump() for item in results]}

    def tutor(self, request: TutorRequest) -> TutorResponse:
        return self._tutor_engine().answer(request)

    def tutor_stream_events(self, request: TutorRequest):
        return self._tutor_engine().stream_events(request)

    def progress(self) -> UserProgress:
        if self._progress_cache is not None:
            return self._progress_cache
        progress_path = self.learning_dir / "progress.json"
        if progress_path.exists():
            try:
                self._progress_cache = UserProgress.model_validate(orjson.loads(progress_path.read_bytes()))
                return self._progress_cache
            except orjson.JSONDecodeError:
                pass
        self._progress_cache = UserProgress()
        return self._progress_cache

    def progress_summary(self) -> ProgressSummary:
        progress = self.progress()
        return ProgressSummary(
            completed_lessons=len(progress.completed_lessons),
            viewed_topics=len(progress.viewed_topics),
            active_path_id=(
                progress.last_visited_context.path_id if progress.last_visited_context else None
            ),
            last_context=progress.last_visited_context,
        )

    def accept_progress_event(self, event: ProgressEvent) -> dict:
        progress = self.progress().model_copy(deep=True)
        now = self._now()

        if event.event_type == "topic_viewed" and event.context.topic_id:
            self._upsert_by_keys(
                progress.viewed_topics,
                {"topic_id": event.context.topic_id, "viewed_at": now},
                ["topic_id"],
            )
        elif event.event_type == "lesson_completed" and event.context.path_id and event.context.lesson_id:
            self._upsert_by_keys(
                progress.completed_lessons,
                {
                    "path_id": event.context.path_id,
                    "lesson_id": event.context.lesson_id,
                    "completed_at": now,
                },
                ["path_id", "lesson_id"],
            )
        elif event.event_type == "path_started" and event.context.path_id:
            progress.last_visited_context = event.context
        elif event.event_type == "goal_updated":
            goal = event.metadata.get("goal")
            if isinstance(goal, str):
                progress.active_learning_goal = goal
        elif event.event_type == "explanation_level_changed":
            level = event.metadata.get("level")
            if level in {"beginner", "intermediate", "advanced"}:
                progress.preferred_explanation_level = level

        progress.last_visited_context = event.context
        self._save_progress(progress)
        self._append_event(event, now)
        return {"accepted": True, "progress": progress.model_dump(), "event": event.model_dump()}

    def recommendations(self) -> dict:
        recs = []
        for index, path in enumerate(self.paths()):
            rec_type = "continue_path" if path.status == "in_progress" else "start_path"
            recs.append(
                Recommendation(
                    id=f"rec-{path.id}",
                    type=rec_type,
                    label=("Continue " if rec_type == "continue_path" else "Start ") + path.title,
                    reason=(
                        "This path is already in progress."
                        if rec_type == "continue_path"
                        else "This starter path is generated from repository graph signals."
                    ),
                    target={"path_id": path.id, "lesson_id": None, "topic_id": None},
                    score=0.95 - (index * 0.05),
                    signals=["path_progress" if rec_type == "continue_path" else "graph_centrality"],
                )
            )
        nodes = self._nodes()
        if nodes:
            first = nodes[0]
            recs.append(
                Recommendation(
                    id="rec-open-topic",
                    type="open_topic",
                    label=f"Open {first.name}",
                    reason="This symbol is available in the current knowledge graph.",
                    target={"path_id": None, "lesson_id": None, "topic_id": first.id},
                    score=0.75,
                    signals=["recent_graph_context"],
                )
            )
        return {"recommendations": [rec.model_dump() for rec in recs]}

    def _learning_paths(self, *, non_blocking: bool = False) -> list[LearningPathDetail]:
        if self._paths_cache is not None:
            return self._paths_cache

        cached = self._load_paths_cache()
        if cached:
            self._paths_cache = cached
            self._path_index_cache = self._build_path_index(cached)
            return cached
        if non_blocking:
            return []

        generated = self._generate_paths()
        self._paths_cache = generated
        self._path_index_cache = self._build_path_index(generated)
        if generated:
            self._store_paths_cache(generated)
        return generated

    def _learning_path_index(self) -> dict[str, LearningPathDetail]:
        if self._path_index_cache is not None:
            return self._path_index_cache
        paths = self._learning_paths()
        self._path_index_cache = self._build_path_index(paths)
        return self._path_index_cache

    def _build_path_index(
        self,
        paths: list[LearningPathDetail],
    ) -> dict[str, LearningPathDetail]:
        return {path.id: path for path in paths}

    def _generate_paths(self) -> list[LearningPathDetail]:
        graph = self._graph()
        if graph is None:
            return []
        nodes, edges = graph
        try:
            hotpath = self.storage.load_hotpath()
        except FileNotFoundError:
            hotpath = {}
        planned = LearningPathPlanner(nodes, edges, hotpath).generate()
        paths = []
        for path in planned.paths:
            paths.append(path.model_copy(update={"warnings": [*path.warnings, *planned.warnings]}))
        return paths

    def _load_paths_cache(self) -> list[LearningPathDetail]:
        cache_path = self.learning_dir / "paths.json"
        if not cache_path.exists():
            return []
        try:
            payload = orjson.loads(cache_path.read_bytes())
        except (OSError, orjson.JSONDecodeError):
            logger.warning("Invalid or unreadable learning paths cache at %s; regenerating.", cache_path)
            return []
        if not isinstance(payload, dict):
            logger.warning("Learning paths cache at %s is not a JSON object; regenerating.", cache_path)
            return []

        graph = self._graph()
        node_count = len(graph[0]) if graph else 0
        edge_count = len(graph[1]) if graph else 0
        expected_key = paths_cache_key(self._load_manifest(), node_count, edge_count)
        if payload.get("cache_key") != expected_key:
            return []

        try:
            return [
                LearningPathDetail.model_validate(path)
                for path in payload.get("paths", [])
                if isinstance(path, dict)
            ]
        except Exception:
            logger.warning("Learning paths cache at %s failed validation; regenerating.", cache_path)
            return []

    def _store_paths_cache(self, paths: list[LearningPathDetail]) -> None:
        graph = self._graph()
        node_count = len(graph[0]) if graph else 0
        edge_count = len(graph[1]) if graph else 0
        payload = {
            "cache_key": paths_cache_key(self._load_manifest(), node_count, edge_count),
            "generated_at": self._now(),
            "paths": [path.model_dump() for path in paths],
        }
        self.learning_dir.mkdir(parents=True, exist_ok=True)
        (self.learning_dir / "paths.json").write_bytes(
            orjson.dumps(payload, option=orjson.OPT_INDENT_2)
        )

    def _summary_from_detail(self, detail: LearningPathDetail) -> LearningPathSummary:
        return LearningPathSummary(
            id=detail.id,
            title=detail.title,
            description=detail.description,
            audience_level=detail.audience_level,
            estimated_minutes=detail.estimated_minutes,
            lesson_count=detail.lesson_count,
            completed_lesson_count=detail.completed_lesson_count,
            prerequisites=detail.prerequisites,
            status=detail.status,
        )

    def _apply_detail_progress(self, detail: LearningPathDetail) -> LearningPathDetail:
        detail = detail.model_copy(deep=True)
        completed_ids = self._completed_lesson_ids(detail.id)
        for lesson in detail.lessons:
            lesson.completed = lesson.id in completed_ids
        completed_count = sum(1 for lesson in detail.lessons if lesson.completed)
        status = self._path_status(completed_count, len(detail.lessons))
        detail.lesson_count = len(detail.lessons)
        detail.completed_lesson_count = completed_count
        detail.status = status
        detail.progress = PathProgress(
            completed_lesson_count=completed_count,
            lesson_count=len(detail.lessons),
            status=status,
        )
        return detail

    def _completed_lesson_ids(self, path_id: str) -> set[str]:
        return {
            item["lesson_id"]
            for item in self.progress().completed_lessons
            if item.get("path_id") == path_id and item.get("lesson_id")
        }

    def _path_status(self, completed_count: int, lesson_count: int) -> str:
        if lesson_count > 0 and completed_count >= lesson_count:
            return "completed"
        if completed_count > 0:
            return "in_progress"
        return "not_started"

    def _recommended_topics(self) -> list[TopicSearchResult]:
        topics = []
        for node in self._nodes()[:5]:
            topics.append(
                TopicSearchResult(
                    id=node.id,
                    type=node.kind.value,
                    title=node.name,
                    summary=f"{node.kind.value} in {node.path}",
                    score=0.8,
                    matched_fields=["graph"],
                )
            )
        return topics

    def _important_features(self) -> list[dict[str, str | int | float | None]]:
        if self._features_cache is None:
            try:
                self._features_cache = self.storage.load_features()
            except FileNotFoundError:
                self._features_cache = []
        features = self._features_cache
        if not features:
            return []
        return [
            {
                "id": feature.id,
                "name": feature.name,
                "member_count": len(feature.member_node_ids),
                "edge_density": feature.edge_density,
            }
            for feature in features[:10]
        ]

    def _next_action(self, paths: list[LearningPathSummary], status: KbStatus) -> NextAction:
        if not status.available:
            return NextAction(type="open_graph", label="Generate the knowledge base", target_id=None)
        if paths:
            return NextAction(type="start_path", label="Start with architecture", target_id=paths[0].id)
        return NextAction(type="ask_tutor", label="Ask the AI tutor", target_id=None)

    def _tutor_engine(self) -> Tutor:
        if self._tutor_cache is not None:
            return self._tutor_cache
        nodes, edges = self._graph() or ([], [])
        kwargs = {
            "nodes": nodes,
            "edges": edges,
            "status": self.kb_status(),
            "project_summary": self.project_summary(),
        }
        factory = self._tutor_factory or default_tutor_factory
        try:
            self._tutor_cache = factory(**kwargs)
        except Exception:
            logger.exception("Learning tutor factory failed; falling back to default tutor.")
            self._tutor_cache = default_tutor_factory(**kwargs)
        if self._tutor_cache is None:
            logger.error("Learning tutor factory returned None; falling back to default tutor.")
            self._tutor_cache = default_tutor_factory(**kwargs)
        return self._tutor_cache

    def _topic_explainer(self) -> TopicExplainer:
        if self._topic_explainer_cache is not None:
            return self._topic_explainer_cache
        nodes, edges = self._graph() or ([], [])
        self._topic_explainer_cache = TopicExplainer(
            nodes=nodes,
            edges=edges,
            status=self.kb_status(),
        )
        return self._topic_explainer_cache

    def _safe_explain_topic(
        self,
        explainer: TopicExplainer,
        topic_id: str,
        *,
        progress: TopicProgress | None = None,
        cached: dict | None = None,
    ) -> TopicPage:
        try:
            return explainer.explain(topic_id, progress=progress, cached=cached)
        except Exception as exc:
            logger.exception("Topic explanation failed for %s.", topic_id)
            return self._topic_error_page(topic_id, exc, progress=progress)

    def _topic_error_page(
        self,
        topic_id: str,
        exc: Exception,
        *,
        progress: TopicProgress | None = None,
    ) -> TopicPage:
        return TopicPage(
            id=topic_id,
            type="unknown",
            title=topic_id,
            summary="Topic explanation failed.",
            explanation="This topic could not be explained because the topic explainer failed.",
            why_it_matters="The learning platform returned a safe fallback instead of failing the request.",
            progress=progress or TopicProgress(),
            warnings=[
                *self.kb_status().warnings,
                WarningInfo(
                    code="topic_explainer_error",
                    message=f"Topic explainer failed with {type(exc).__name__}.",
                ),
            ],
        )

    def _topic_has_error(self, page: TopicPage) -> bool:
        return any(warning.code == "topic_explainer_error" for warning in page.warnings)

    def _topic_cache_key(self, topic_id: str) -> str:
        manifest = self._load_manifest() or {}
        kb_version = (
            manifest.get("version")
            or manifest.get("created_at")
            or manifest.get("source_repo")
            or "unknown"
        )
        raw_key = f"{kb_version}:{TOPIC_PROMPT_VERSION}:{topic_id}"
        return f"topic:{sha256(raw_key.encode('utf-8')).hexdigest()}"

    def _load_topic_cache(self) -> dict[str, dict]:
        if self._topic_cache is not None:
            return self._topic_cache
        cache_path = self.learning_dir / "topics.json"
        if not cache_path.exists():
            self._topic_cache = {}
            return self._topic_cache
        try:
            payload = orjson.loads(cache_path.read_bytes())
        except (OSError, orjson.JSONDecodeError):
            logger.warning("Invalid or unreadable topic cache at %s; ignoring it.", cache_path)
            self._topic_cache = {}
            return self._topic_cache
        if not isinstance(payload, dict):
            logger.warning("Topic cache at %s is not a JSON object; ignoring it.", cache_path)
            self._topic_cache = {}
            return self._topic_cache
        self._topic_cache = payload
        return self._topic_cache

    def _store_topic_cache(self, page: TopicPage) -> None:
        cache = self._load_topic_cache()
        # TODO(Phase 7): cap this generated topic cache and evict least-recently used entries.
        cache[self._topic_cache_key(page.id)] = cache_payload(page)
        self.learning_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.learning_dir / "topics.json"
        cache_path.write_bytes(orjson.dumps(cache, option=orjson.OPT_INDENT_2))

    def _load_manifest(self) -> dict | None:
        if self._manifest_cache is not _UNSET:
            return self._manifest_cache  # type: ignore[return-value]
        manifest_path = self.kb_dir / "manifest.json"
        if not manifest_path.exists():
            self._manifest_cache = None
            return None
        try:
            self._manifest_cache = orjson.loads(manifest_path.read_bytes())
            return self._manifest_cache
        except orjson.JSONDecodeError:
            self._manifest_cache = None
            return None

    def _entry_count(self, manifest: dict) -> int:
        manifest_total = manifest.get("stats", {}).get("total_entries")
        if isinstance(manifest_total, int):
            return manifest_total
        if self.entries_dir.exists():
            return sum(1 for path in self.entries_dir.glob("*.json") if path.is_file())
        return 0

    def _arch_summary(self) -> str | None:
        arch_path = self.entries_dir / "arch_root.json"
        if not arch_path.exists():
            return None
        try:
            entry = orjson.loads(arch_path.read_bytes())
        except orjson.JSONDecodeError:
            return None
        ai = entry.get("ai", {})
        return ai.get("summary") or ai.get("purpose")

    def _nodes(self, node_ids: list[str] | None = None) -> list[SymbolNode]:
        graph = self._graph(node_ids)
        if graph is None:
            return []
        nodes, _ = graph
        return sorted(nodes, key=lambda node: (node.path, node.name, node.id))

    def _graph(self, node_ids: list[str] | None = None) -> GraphCache | None:
        if self._graph_cache is not _UNSET:
            graph = self._graph_cache  # type: ignore[assignment]
        else:
            try:
                graph = self.storage.load()
            except FileNotFoundError:
                graph = None
            self._graph_cache = graph

        if graph is None:
            return None
        if not node_ids:
            return graph

        node_id_set = set(node_ids)
        nodes, edges = graph
        filtered_nodes = [node for node in nodes if node.id in node_id_set]
        filtered_edges = [
            edge for edge in edges
            if edge.source in node_id_set or edge.target in node_id_set
        ]
        return filtered_nodes, filtered_edges

    def _save_progress(self, progress: UserProgress) -> None:
        self.learning_dir.mkdir(parents=True, exist_ok=True)
        progress_path = self.learning_dir / "progress.json"
        progress_path.write_bytes(orjson.dumps(progress.model_dump(), option=orjson.OPT_INDENT_2))
        self._progress_cache = progress

    def _append_event(self, event: ProgressEvent, occurred_at: str) -> None:
        self.learning_dir.mkdir(parents=True, exist_ok=True)
        event_path = self.learning_dir / "events.jsonl"
        payload = {**event.model_dump(), "occurred_at": occurred_at}
        with event_path.open("ab") as fh:
            fh.write(orjson.dumps(payload))
            fh.write(b"\n")

    def _upsert_by_keys(self, items: list[dict[str, str]], item: dict[str, str], keys: list[str]) -> None:
        for index, existing in enumerate(items):
            if all(existing.get(key) == item.get(key) for key in keys):
                items[index] = item
                return
        items.append(item)

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
