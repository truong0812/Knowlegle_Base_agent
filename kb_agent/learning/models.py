"""Models for the AI learning platform API contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ContextPage = Literal["dashboard", "path", "topic", "tutor", "graph", "unknown"]
ExplanationLevel = Literal["beginner", "intermediate", "advanced"]
LearningStatus = Literal["not_started", "in_progress", "completed"]
RecommendationType = Literal["start_path", "continue_path", "open_topic", "ask_tutor", "open_graph"]
ProgressEventType = Literal[
    "topic_viewed",
    "lesson_completed",
    "path_started",
    "goal_updated",
    "context_changed",
    "explanation_level_changed",
]


class WarningInfo(BaseModel):
    """Structured warning that does not prevent a response."""

    code: str
    message: str


class Citation(BaseModel):
    """Source citation for a learning response."""

    label: str
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    entry_id: str | None = None
    node_id: str | None = None


class LearningContext(BaseModel):
    """Current UI or learning context."""

    page: ContextPage = "unknown"
    topic_id: str | None = None
    path_id: str | None = None
    lesson_id: str | None = None
    selected_text: str | None = None


class KbStatus(BaseModel):
    """Knowledge base availability summary for learning APIs."""

    available: bool = False
    node_count: int = 0
    edge_count: int = 0
    entry_count: int = 0
    warnings: list[WarningInfo] = Field(default_factory=list)


class ProjectSummary(BaseModel):
    """Project metadata shown on the learning dashboard."""

    project_name: str
    description: str | None = None
    source_repo: str | None = None
    created_at: str | None = None


class ProgressSummary(BaseModel):
    """Small single-user progress summary."""

    completed_lessons: int = 0
    viewed_topics: int = 0
    active_path_id: str | None = None
    last_context: LearningContext | None = None


class NextAction(BaseModel):
    """Suggested action for the learner."""

    type: RecommendationType
    label: str
    target_id: str | None = None


class LearningPathSummary(BaseModel):
    """Compact path card."""

    id: str
    title: str
    description: str
    audience_level: ExplanationLevel = "beginner"
    estimated_minutes: int = 20
    lesson_count: int = 0
    completed_lesson_count: int = 0
    prerequisites: list[str] = Field(default_factory=list)
    status: LearningStatus = "not_started"


class LearningLesson(BaseModel):
    """Single learning path lesson."""

    id: str
    title: str
    summary: str
    explanation: str
    key_concepts: list[str] = Field(default_factory=list)
    related_topics: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    completed: bool = False
    next_lesson_id: str | None = None


class PathProgress(BaseModel):
    """Progress for a single learning path."""

    completed_lesson_count: int = 0
    lesson_count: int = 0
    status: LearningStatus = "not_started"


class LearningPathDetail(LearningPathSummary):
    """Full path with ordered lessons."""

    objectives: list[str] = Field(default_factory=list)
    lessons: list[LearningLesson] = Field(default_factory=list)
    progress: PathProgress = Field(default_factory=PathProgress)
    warnings: list[WarningInfo] = Field(default_factory=list)


class TopicSearchResult(BaseModel):
    """Search result for topic lookup."""

    id: str
    type: str
    title: str
    summary: str
    score: float = 0.0
    matched_fields: list[str] = Field(default_factory=list)


class TopicProgress(BaseModel):
    """Per-topic lightweight progress."""

    viewed: bool = False
    last_viewed_at: str | None = None


class TopicPage(BaseModel):
    """Learner-friendly topic page."""

    id: str
    type: str
    title: str
    summary: str
    explanation: str
    why_it_matters: str
    examples: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    related_topics: list[str] = Field(default_factory=list)
    related_symbols: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    progress: TopicProgress = Field(default_factory=TopicProgress)
    suggested_questions: list[str] = Field(default_factory=list)
    graph_context: dict[str, list[dict]] = Field(
        default_factory=lambda: {"nodes": [], "relationships": []}
    )
    warnings: list[WarningInfo] = Field(default_factory=list)


class TutorRequest(BaseModel):
    """Request body for the learning tutor endpoint."""

    message: str
    stream: bool = False
    context: LearningContext = Field(default_factory=LearningContext)
    learner: dict[str, str] = Field(default_factory=lambda: {"level": "beginner"})


class TutorResponse(BaseModel):
    """Natural-language tutor response contract."""

    answer: str
    summary: str
    key_concepts: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    recommended_next_steps: list[NextAction] = Field(default_factory=list)
    related_topics: list[str] = Field(default_factory=list)
    graph_context: dict[str, list[dict]] = Field(
        default_factory=lambda: {"nodes": [], "relationships": []}
    )
    warnings: list[WarningInfo] = Field(default_factory=list)


class ProgressEvent(BaseModel):
    """Client event that updates lightweight learner state."""

    event_type: ProgressEventType
    context: LearningContext = Field(default_factory=LearningContext)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class UserProgress(BaseModel):
    """Single-user progress payload."""

    completed_lessons: list[dict[str, str]] = Field(default_factory=list)
    viewed_topics: list[dict[str, str]] = Field(default_factory=list)
    preferred_explanation_level: ExplanationLevel = "beginner"
    active_learning_goal: str | None = None
    last_visited_context: LearningContext | None = None


class Recommendation(BaseModel):
    """Ranked next action."""

    id: str
    type: RecommendationType
    label: str
    reason: str
    target: dict[str, str | None] = Field(default_factory=dict)
    score: float = 0.0
    signals: list[str] = Field(default_factory=list)


class DashboardResponse(BaseModel):
    """Learning dashboard response."""

    summary: ProjectSummary
    kb_status: KbStatus
    progress: ProgressSummary
    recommended_paths: list[LearningPathSummary] = Field(default_factory=list)
    recommended_topics: list[TopicSearchResult] = Field(default_factory=list)
    important_features: list[dict[str, str | int | float | None]] = Field(default_factory=list)
    recent_activity: list[dict[str, str]] = Field(default_factory=list)
    suggested_next_action: NextAction
