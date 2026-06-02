"""Deterministic Phase 1 API helpers for the learning platform."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import logging
from pathlib import Path

import orjson

from kb_agent.graph.storage import GraphStorage, ReadOnlyStorage
from kb_agent.learning.citations import citation_from_node
from kb_agent.learning.models import (
    DashboardResponse,
    KbStatus,
    LearningLesson,
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

    def paths(self) -> list[LearningPathSummary]:
        return [self._apply_path_progress(path) for path in self._starter_paths()]

    def path_detail(self, path_id: str) -> LearningPathDetail | None:
        summary = next((path for path in self._starter_paths() if path.id == path_id), None)
        if summary is None:
            return None
        lessons = self._lessons_for_path(summary.id)
        completed_ids = self._completed_lesson_ids(path_id)
        for lesson in lessons:
            lesson.completed = lesson.id in completed_ids
        completed_count = sum(1 for lesson in lessons if lesson.completed)
        status = self._path_status(completed_count, len(lessons))
        return LearningPathDetail(
            id=summary.id,
            title=summary.title,
            description=summary.description,
            audience_level=summary.audience_level,
            estimated_minutes=summary.estimated_minutes,
            prerequisites=summary.prerequisites,
            lesson_count=len(lessons),
            completed_lesson_count=completed_count,
            status=status,
            objectives=[
                "Understand the purpose of this area.",
                "Connect important concepts to source references.",
                "Know what to inspect next.",
            ],
            lessons=lessons,
            progress=PathProgress(
                completed_lesson_count=completed_count,
                lesson_count=len(lessons),
                status=status,
            ),
        )

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
        node = self._node_by_id_or_name(topic_id)
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
            return TopicPage(
                id=node.id,
                type=node.kind.value,
                title=node.name,
                summary=f"{node.name} is a {node.kind.value} in {node.path}.",
                explanation=(
                    f"{node.name} belongs to {node.path}. Phase 1 returns a stable "
                    "contract; later phases will generate richer natural-language explanations."
                ),
                why_it_matters="This topic is part of the source graph and can anchor learning context.",
                examples=[node.signature] if node.signature else [],
                related_symbols=[],
                citations=[citation_from_node(node)],
                progress=TopicProgress(
                    viewed=True,
                    last_viewed_at=topic_progress.get("viewed_at"),
                ),
                suggested_questions=[
                    f"What does {node.name} do?",
                    f"What calls {node.name}?",
                    f"What should I learn before {node.name}?",
                ],
                graph_context={
                    "nodes": [{"id": node.id, "name": node.name, "kind": node.kind.value}],
                    "relationships": [],
                },
            )

        warning = WarningInfo(code="topic_not_found", message="Topic was not found in the current graph.")
        return TopicPage(
            id=topic_id,
            type="unknown",
            title=topic_id,
            summary="Topic not found.",
            explanation="This topic is not available in the current knowledge graph.",
            why_it_matters="Generate or refresh the knowledge base to make this topic available.",
            warnings=[warning],
        )

    def search_topics(self, query: str) -> dict:
        q = query.strip().lower()
        if not q:
            return {"query": query, "results": []}
        results = []
        for node in self._nodes():
            haystack = f"{node.name} {node.path} {node.kind.value}".lower()
            if not q or q in haystack:
                score = 1.0 if q and q in node.name.lower() else 0.75
                results.append(
                    TopicSearchResult(
                        id=node.id,
                        type=node.kind.value,
                        title=node.name,
                        summary=f"{node.kind.value} in {node.path}",
                        score=score,
                        matched_fields=["title" if q in node.name.lower() else "summary"],
                    )
                )
        results.sort(key=lambda item: (-item.score, item.title, item.id))
        return {"query": query, "results": [item.model_dump() for item in results[:20]]}

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
        recs = [
            Recommendation(
                id="rec-start-architecture",
                type="start_path",
                label="Start with Architecture overview",
                reason="Architecture is the broadest entry point into the repository.",
                target={"path_id": "architecture-overview", "lesson_id": None, "topic_id": None},
                score=0.95,
                signals=["prerequisite", "graph_centrality"],
            )
        ]
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

    def _starter_paths(self) -> list[LearningPathSummary]:
        return [
            LearningPathSummary(
                id="architecture-overview",
                title="Architecture overview",
                description="Understand the repository shape, main modules, and entry points.",
                estimated_minutes=20,
                lesson_count=3,
            ),
            LearningPathSummary(
                id="query-and-retrieval",
                title="Query and retrieval pipeline",
                description="Follow how questions become source-grounded retrieval context.",
                estimated_minutes=25,
                lesson_count=3,
                prerequisites=["architecture-overview"],
            ),
            LearningPathSummary(
                id="knowledge-graph-construction",
                title="Knowledge graph construction",
                description="Learn how symbols, edges, features, and graph signals are built.",
                estimated_minutes=30,
                lesson_count=3,
                prerequisites=["architecture-overview"],
            ),
        ]

    def _lessons_for_path(self, path_id: str) -> list[LearningLesson]:
        base = {
            "architecture-overview": [
                ("lesson-1", "Repository shape", "Learn the top-level modules and generated KB structure."),
                ("lesson-2", "Core pipeline", "Connect analyzer, graph, indexer, and query layers."),
                ("lesson-3", "Where to inspect next", "Use topics and graph context to continue learning."),
            ],
            "query-and-retrieval": [
                ("lesson-1", "Query entry point", "Understand how a user question enters the system."),
                ("lesson-2", "Context expansion", "Follow semantic retrieval plus graph expansion."),
                ("lesson-3", "Composed answer context", "See how citations and source context are assembled."),
            ],
            "knowledge-graph-construction": [
                ("lesson-1", "Symbol nodes", "Understand graph nodes from parsed source symbols."),
                ("lesson-2", "Relationships", "Understand calls, imports, contains, and type-use edges."),
                ("lesson-3", "Graph signals", "Understand hot-path and centrality-style signals."),
            ],
        }
        items = base.get(path_id, [])
        lessons = []
        for index, (lesson_id, title, summary) in enumerate(items):
            next_lesson_id = items[index + 1][0] if index + 1 < len(items) else None
            lessons.append(
                LearningLesson(
                    id=lesson_id,
                    title=title,
                    summary=summary,
                    explanation=summary,
                    key_concepts=["source", "graph", "learning"],
                    related_topics=[],
                    citations=[],
                    next_lesson_id=next_lesson_id,
                )
            )
        return lessons

    def _apply_path_progress(self, path: LearningPathSummary) -> LearningPathSummary:
        detail_lessons = self._lessons_for_path(path.id)
        completed_count = len(self._completed_lesson_ids(path.id))
        completed_count = min(completed_count, len(detail_lessons))
        return path.model_copy(
            update={
                "lesson_count": len(detail_lessons),
                "completed_lesson_count": completed_count,
                "status": self._path_status(completed_count, len(detail_lessons)),
            }
        )

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

    def _node_by_id_or_name(self, topic_id: str) -> SymbolNode | None:
        for node in self._nodes():
            if node.id == topic_id or node.name == topic_id:
                return node
        return None

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
