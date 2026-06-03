"""Personalized recommendation scoring for the learning platform."""
from __future__ import annotations

from dataclasses import dataclass

from kb_agent.graph.hotpath import HotPathScore
from kb_agent.learning.models import (
    LearningPathSummary,
    Recommendation,
    TopicSearchResult,
    UserProgress,
)
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode


@dataclass(frozen=True)
class RecommendationResult:
    """Ranked next actions and topic cards derived from learner state."""

    recommendations: list[Recommendation]
    topics: list[TopicSearchResult]


class LearningRecommendationEngine:
    """Rank next steps using path progress, graph relationships, and learner memory."""

    def __init__(
        self,
        *,
        paths: list[LearningPathSummary],
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
        hotpath: dict[str, HotPathScore],
        progress: UserProgress,
    ) -> None:
        self._paths = paths
        self._nodes = nodes
        self._edges = edges
        self._hotpath = hotpath
        self._progress = progress
        self._node_by_id = {node.id: node for node in nodes}
        self._viewed_topic_ids = {
            item.get("topic_id")
            for item in progress.viewed_topics
            if item.get("topic_id")
        }
        self._path_by_id = {path.id: path for path in paths}

    def generate(self, *, limit: int = 8) -> RecommendationResult:
        """Return personalized recommendations and topic cards."""
        recommendations = [
            *self._path_recommendations(),
            *self._topic_recommendations(),
        ]
        ranked = sorted(
            self._dedupe_recommendations(recommendations),
            key=lambda rec: (-rec.score, rec.label, rec.id),
        )[:limit]
        topics = self._topic_cards(limit=5)
        return RecommendationResult(recommendations=ranked, topics=topics)

    def _path_recommendations(self) -> list[Recommendation]:
        recommendations: list[Recommendation] = []
        for index, path in enumerate(self._paths):
            next_lesson_id = self._next_lesson_id(path)
            missing_prereq = self._missing_prerequisite(path)
            if missing_prereq is not None:
                prereq = self._path_by_id[missing_prereq]
                signals = ["prerequisite", "path_order"]
                scored_signals = self._score_signals(prereq.title, prereq.id, signals=signals)
                recommendations.append(
                    Recommendation(
                        id=f"rec-prereq-{path.id}-{missing_prereq}",
                        type="continue_path" if prereq.status == "in_progress" else "start_path",
                        label=f"Learn prerequisite: {prereq.title}",
                        reason=f"{prereq.title} comes before {path.title}.",
                        target={
                            "path_id": prereq.id,
                            "lesson_id": self._next_lesson_id(prereq),
                            "topic_id": None,
                        },
                        score=self._score(
                            0.86 - (index * 0.02),
                            prereq.title,
                            prereq.id,
                        ),
                        signals=scored_signals,
                    )
                )
                continue

            if path.status == "completed":
                continue

            rec_type = "continue_path" if path.status == "in_progress" else "start_path"
            signals = ["incomplete_path"] if path.status == "in_progress" else ["graph_centrality"]
            if path.status == "in_progress":
                signals.append("path_progress")
            scored_signals = self._score_signals(path.title, path.id, signals=signals)
            recommendations.append(
                Recommendation(
                    id=f"rec-{path.id}",
                    type=rec_type,
                    label=("Continue " if rec_type == "continue_path" else "Start ") + path.title,
                    reason=(
                        "You have started this path; the next unfinished lesson is ready."
                        if rec_type == "continue_path"
                        else "This starter path is generated from repository graph signals."
                    ),
                    target={"path_id": path.id, "lesson_id": next_lesson_id, "topic_id": None},
                    score=self._score(
                        (0.95 if path.status == "in_progress" else 0.78) - (index * 0.03),
                        path.title,
                        path.id,
                    ),
                    signals=scored_signals,
                )
            )
        return recommendations

    def _topic_recommendations(self) -> list[Recommendation]:
        recommendations: list[Recommendation] = []
        for node, signals, base_score, reason in self._ranked_topic_candidates():
            scored_signals = self._score_signals(node.name, node.path, signals=signals)
            recommendations.append(
                Recommendation(
                    id=f"rec-topic-{self._stable_id(node.id)}",
                    type="open_topic",
                    label=f"Open {node.name}",
                    reason=reason,
                    target={"path_id": None, "lesson_id": None, "topic_id": node.id},
                    score=self._score(base_score, node.name, node.path),
                    signals=scored_signals,
                )
            )
        return recommendations[:8]

    def _topic_cards(self, *, limit: int) -> list[TopicSearchResult]:
        cards: list[TopicSearchResult] = []
        for node, signals, base_score, _reason in self._ranked_topic_candidates():
            scored_signals = self._score_signals(node.name, node.path, signals=signals)
            cards.append(
                TopicSearchResult(
                    id=node.id,
                    type=node.kind.value,
                    title=node.name,
                    summary=f"{node.kind.value} in {node.path}",
                    score=round(self._score(base_score, node.name, node.path), 4),
                    matched_fields=scored_signals,
                )
            )
            if len(cards) >= limit:
                break
        return cards

    def _ranked_topic_candidates(self) -> list[tuple[SymbolNode, list[str], float, str]]:
        candidates: dict[str, tuple[SymbolNode, list[str], float, str]] = {}

        for topic_id in sorted(self._viewed_topic_ids):
            for edge in self._edges:
                if (
                    edge.target == topic_id
                    and edge.source in self._node_by_id
                    and relationship_is_prerequisite(edge)
                ):
                    node = self._node_by_id[edge.source]
                    if node.id not in self._viewed_topic_ids:
                        self._set_topic_candidate(
                            candidates,
                            node,
                            ["prerequisite", "recently_viewed_topic"],
                            0.88 + (edge.confidence * 0.05),
                            "This prerequisite connects to a topic you recently viewed.",
                        )
                if edge.source == topic_id and edge.target in self._node_by_id:
                    node = self._node_by_id[edge.target]
                    if node.id not in self._viewed_topic_ids:
                        self._set_topic_candidate(
                            candidates,
                            node,
                            ["related_topic", "recently_viewed_topic"],
                            0.62 + (edge.confidence * 0.05),
                            "This related topic extends what you recently viewed.",
                        )

        for index, node in enumerate(self._nodes):
            if node.id in self._viewed_topic_ids:
                continue
            hot = self._hotpath.get(node.id)
            hotness = getattr(hot, "hotness", 0.0)
            incoming = getattr(hot, "incoming_calls", 0)
            signals = ["hot_path"] if hotness else ["graph_centrality"]
            self._set_topic_candidate(
                candidates,
                node,
                signals,
                0.52 + hotness * 0.2 - index * 0.005,
                (
                    "This hot-path symbol appears central in the current graph."
                    if hotness
                    else "This symbol is available in the current knowledge graph."
                ),
            )
            if incoming:
                current = candidates[node.id]
                merged = [*current[1], "incoming_calls"]
                candidates[node.id] = (current[0], self._dedupe_strings(merged), current[2], current[3])

        return sorted(
            candidates.values(),
            key=lambda item: (
                -self._score(
                    item[2],
                    item[0].name,
                    item[0].path,
                ),
                item[0].path,
                item[0].name,
            ),
        )

    def _set_topic_candidate(
        self,
        candidates: dict[str, tuple[SymbolNode, list[str], float, str]],
        node: SymbolNode,
        signals: list[str],
        score: float,
        reason: str,
    ) -> None:
        existing = candidates.get(node.id)
        if existing is None or score > existing[2]:
            candidates[node.id] = (node, self._dedupe_strings(signals), score, reason)
            return
        if existing is not None:
            merged_signals = self._dedupe_strings([*existing[1], *signals])
            candidates[node.id] = (
                existing[0],
                merged_signals,
                existing[2],
                self._merge_reason(existing[3], reason, existing[1], signals),
            )

    def _next_lesson_id(self, path: LearningPathSummary) -> str | None:
        if path.status == "completed":
            return None
        return f"lesson-{path.completed_lesson_count + 1}"

    def _missing_prerequisite(self, path: LearningPathSummary) -> str | None:
        for prereq_id in path.prerequisites:
            prereq = self._path_by_id.get(prereq_id)
            if prereq is not None and prereq.status != "completed":
                return prereq_id
        return None

    def _score(self, base: float, *texts: str) -> float:
        score = base
        goal = (self._progress.active_learning_goal or "").strip().lower()
        if goal and any(goal in text.lower() for text in texts):
            score += 0.12
        if self._progress.last_visited_context and self._progress.last_visited_context.path_id:
            path_id = self._progress.last_visited_context.path_id
            if any(path_id == text for text in texts):
                score += 0.04
        return round(min(score, 1.0), 4)

    def _score_signals(self, *texts: str, signals: list[str]) -> list[str]:
        scored = [*signals]
        goal = (self._progress.active_learning_goal or "").strip().lower()
        if goal and any(goal in text.lower() for text in texts):
            scored.append("active_goal")
        if self._progress.last_visited_context and self._progress.last_visited_context.path_id:
            path_id = self._progress.last_visited_context.path_id
            if any(path_id == text for text in texts):
                scored.append("last_context")
        return self._dedupe_strings(scored)

    def _dedupe_recommendations(self, recommendations: list[Recommendation]) -> list[Recommendation]:
        best_by_target: dict[tuple[str | None, str | None, str | None, str], Recommendation] = {}
        for rec in recommendations:
            normalized = rec.model_copy(update={"signals": self._dedupe_strings(rec.signals)})
            key = (
                normalized.target.get("path_id"),
                normalized.target.get("lesson_id"),
                normalized.target.get("topic_id"),
                normalized.type,
            )
            existing = best_by_target.get(key)
            if existing is None or normalized.score > existing.score:
                best_by_target[key] = normalized
        return list(best_by_target.values())

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        return [value for value in values if not (value in seen or seen.add(value))]

    def _merge_reason(
        self,
        existing_reason: str,
        new_reason: str,
        existing_signals: list[str],
        new_signals: list[str],
    ) -> str:
        if existing_reason == new_reason or set(new_signals).issubset(set(existing_signals)):
            return existing_reason
        return f"Multiple graph signals point to this topic. Strongest reason: {existing_reason}"

    def _stable_id(self, value: str) -> str:
        return (
            value.replace("\\", "-")
            .replace("/", "-")
            .replace(":", "-")
            .replace(" ", "-")
        )


def relationship_is_prerequisite(edge: SymbolEdge) -> bool:
    """Return whether an edge can imply a learner prerequisite."""
    return edge.kind in {
        EdgeKind.CALLS,
        EdgeKind.IMPORTS,
        EdgeKind.USES_TYPE,
        EdgeKind.INHERITS,
        EdgeKind.IMPLEMENTS,
    }
