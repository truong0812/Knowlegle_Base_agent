"""Natural-language tutor synthesis for the learning platform."""
from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
from typing import Protocol

from kb_agent.learning.citations import citation_from_node
from kb_agent.learning.models import (
    Citation,
    KbStatus,
    LearningContext,
    NextAction,
    ProjectSummary,
    TutorRequest,
    TutorResponse,
    WarningInfo,
)
from kb_agent.models.graph import SymbolEdge, SymbolNode


logger = logging.getLogger(__name__)

PROMPT_VERSION = "tutor_answer.v1"
PROMPT_TEMPLATE_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.txt"
MAX_CONTEXT_NODES = 5
MAX_CONTEXT_RELATIONSHIPS = 8
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "how",
    "the",
    "this",
    "what",
    "with",
}


class TutorLLMClient(Protocol):
    """Small interface for future provider-backed tutor synthesis."""

    model_name: str

    def complete(self, prompt: str, context: "TutorContext") -> TutorResponse:
        """Return a full tutor response for the supplied prompt and context."""

    def stream(self, prompt: str, context: "TutorContext") -> Iterable[str]:
        """Yield response text chunks when the provider supports streaming."""


class Tutor(Protocol):
    """Interface for tutor engines used by LearningApi.

    Any object with ``answer`` and ``stream_events`` methods satisfying
    these signatures can be injected via ``LearningApi(tutor_factory=...)``.
    """

    def answer(self, request: TutorRequest) -> TutorResponse: ...

    def stream_events(self, request: TutorRequest) -> Iterator[dict]: ...


@dataclass(frozen=True)
class TutorContext:
    """Retrieved graph context used to synthesize a tutor answer."""

    nodes: list[SymbolNode]
    relationships: list[SymbolEdge]
    citations: list[Citation]
    graph_context: dict[str, list[dict]]
    warnings: list[WarningInfo]


class LearningTutor:
    """Build context and synthesize learner-friendly tutor responses."""

    def __init__(
        self,
        *,
        nodes: Sequence[SymbolNode],
        edges: Sequence[SymbolEdge],
        status: KbStatus,
        project_summary: ProjectSummary,
        llm_client: TutorLLMClient | None = None,
    ) -> None:
        self.nodes = list(nodes)
        self.edges = list(edges)
        self.status = status
        self.project_summary = project_summary
        self.llm_client = llm_client or None

    def answer(self, request: TutorRequest) -> TutorResponse:
        """Return a non-streaming tutor response."""

        context = self.build_context(request)
        if self.llm_client is not None:
            try:
                return self.llm_client.complete(self._prompt(request, context), context)
            except Exception as exc:
                logger.exception("Tutor provider completion failed; falling back to deterministic answer.")
                context.warnings.append(
                    WarningInfo(
                        code="llm_error",
                        message=(
                            "Tutor provider failed; returned deterministic fallback. "
                            f"Error type: {type(exc).__name__}."
                        ),
                    )
                )

        return self._fallback_answer(request, context)

    def stream_events(self, request: TutorRequest) -> Iterator[dict]:
        """Yield structured Server-Sent Event payloads."""

        context = self.build_context(request)
        yield {
            "event": "status",
            "data": {
                "message": "Building source-grounded tutor context.",
                "prompt_version": PROMPT_VERSION,
            },
        }

        if self.llm_client is not None:
            try:
                yield from self._stream_llm_response(request, context)
                return
            except Exception as exc:
                logger.exception("Tutor provider streaming failed; falling back to deterministic answer.")
                context.warnings.append(
                    WarningInfo(
                        code="llm_stream_error",
                        message=(
                            "Tutor provider streaming failed; returned deterministic fallback. "
                            f"Error type: {type(exc).__name__}."
                        ),
                    )
                )

        response = self._fallback_answer(request, context)
        # TODO(Phase 2 provider integration): this deterministic fallback emits
        # prebuilt text chunks. Real first-token latency comes from TutorLLMClient.stream().
        for token in _token_chunks(response.answer):
            yield {"event": "token", "data": {"text": token}}
        yield from self._metadata_events(response)

    def _stream_llm_response(self, request: TutorRequest, context: TutorContext) -> Iterator[dict]:
        answer_parts: list[str] = []
        prompt = self._prompt(request, context)
        for token in self.llm_client.stream(prompt, context):
            answer_parts.append(token)
            yield {"event": "token", "data": {"text": token}}

        metadata_response = self._fallback_answer(request, context)
        response = metadata_response.model_copy(
            update={
                "answer": "".join(answer_parts),
                "summary": "Streamed tutor response.",
            }
        )
        yield from self._metadata_events(response)

    def _metadata_events(self, response: TutorResponse) -> Iterator[dict]:
        for citation in response.citations:
            yield {"event": "citation", "data": citation.model_dump()}
        yield {
            "event": "suggested_questions",
            "data": {"items": response.suggested_questions},
        }
        yield {
            "event": "recommended_next_steps",
            "data": {"items": [step.model_dump() for step in response.recommended_next_steps]},
        }
        yield {"event": "done", "data": response.model_dump()}

    def build_context(self, request: TutorRequest) -> TutorContext:
        """Select a small source-grounded context from the graph."""

        warnings = list(self.status.warnings)
        if not self.status.available:
            warnings.append(
                WarningInfo(
                    code="missing_kb",
                    message="Knowledge base not found. Tutor is using available request context only.",
                )
            )
        if not self.nodes:
            warnings.append(
                WarningInfo(
                    code="missing_graph_context",
                    message="No graph nodes are available for source-grounded tutor context.",
                )
            )

        context_nodes = self._context_nodes(request)
        context_node_ids = {node.id for node in context_nodes}
        relationships = [
            edge
            for edge in self.edges
            if edge.source in context_node_ids or edge.target in context_node_ids
        ][:MAX_CONTEXT_RELATIONSHIPS]
        citations = _dedupe_citations([citation_from_node(node) for node in context_nodes])
        node_lookup = {node.id: node for node in self.nodes}

        return TutorContext(
            nodes=context_nodes,
            relationships=relationships,
            citations=citations,
            graph_context={
                "nodes": [
                    {
                        "id": node.id,
                        "name": node.name,
                        "kind": node.kind.value,
                        "path": node.path,
                    }
                    for node in context_nodes
                ],
                "relationships": [
                    {
                        "source": edge.source,
                        "source_name": getattr(node_lookup.get(edge.source), "name", edge.source),
                        "target": edge.target,
                        "target_name": getattr(node_lookup.get(edge.target), "name", edge.target),
                        "kind": _friendly_edge_label(edge.kind.value),
                        "confidence": edge.confidence,
                    }
                    for edge in relationships
                ],
            },
            warnings=warnings,
        )

    def _context_nodes(self, request: TutorRequest) -> list[SymbolNode]:
        if not self.nodes:
            return []

        scored: dict[str, tuple[int, SymbolNode]] = {}

        def add(node: SymbolNode, score: int) -> None:
            current = scored.get(node.id)
            if current is None or score > current[0]:
                scored[node.id] = (score, node)

        topic_id = request.context.topic_id
        for node in self.nodes:
            if topic_id and (node.id == topic_id or node.name == topic_id):
                add(node, 100)

        tokens = _tokens(
            " ".join(
                part
                for part in [
                    request.message,
                    request.context.selected_text or "",
                    request.context.lesson_id or "",
                    request.context.path_id or "",
                ]
                if part
            )
        )
        for node in self.nodes:
            haystack = f"{node.name} {node.path} {node.kind.value}".lower()
            token_hits = sum(1 for token in tokens if token in haystack)
            if token_hits:
                add(node, 20 + token_hits)

        if not scored:
            for node in sorted(self.nodes, key=lambda item: (item.path, item.name, item.id))[
                :MAX_CONTEXT_NODES
            ]:
                add(node, 5)

        return [
            item[1]
            for item in sorted(
                scored.values(),
                key=lambda item: (-item[0], item[1].path, item[1].name, item[1].id),
            )[:MAX_CONTEXT_NODES]
        ]

    def _fallback_answer(self, request: TutorRequest, context: TutorContext) -> TutorResponse:
        level = request.learner.get("level", "beginner")
        node_names = [node.name for node in context.nodes]
        project = self.project_summary.project_name
        intro = _intent_intro(request.message, request.context)

        if context.nodes:
            primary = context.nodes[0]
            answer = (
                f"{intro} In {project}, a good anchor is `{primary.name}` in "
                f"`{primary.path}`. It is a {primary.kind.value}, so read it as one concrete "
                "piece of the larger flow instead of starting with the whole graph."
            )
            if primary.signature:
                answer += f" Its signature is `{primary.signature}`."
            if len(context.nodes) > 1:
                answer += (
                    " Nearby concepts worth keeping in view are "
                    f"{', '.join(f'`{name}`' for name in node_names[1:])}."
                )
            if context.relationships:
                first_edge = context.relationships[0]
                answer += (
                    " The graph also shows that this area "
                    f"{_friendly_edge_label(first_edge.kind.value)} another symbol, which is useful "
                    "supporting context when you trace behavior."
                )
        else:
            answer = (
                f"{intro} I do not have source graph context yet, so the safest next step is to "
                "start with the architecture overview and refresh the knowledge base if needed."
            )

        if level == "beginner":
            answer += " Start with purpose, then inputs and outputs, then follow one cited source reference."
        elif level == "advanced":
            answer += " For a deeper pass, inspect callers, dependencies, and how this node affects retrieval context."

        warnings = list(context.warnings)
        if self.llm_client is None:
            warnings.append(
                WarningInfo(
                    code="llm_unavailable",
                    message="No tutor LLM client is configured; returned deterministic fallback.",
                )
            )

        return TutorResponse(
            answer=answer,
            summary=_summary(request.message, node_names),
            key_concepts=_key_concepts(context),
            citations=context.citations,
            suggested_questions=_suggested_questions(context, request.context),
            recommended_next_steps=_next_steps(context),
            related_topics=[node.id for node in context.nodes[1:]],
            graph_context=context.graph_context,
            warnings=_dedupe_warnings(warnings),
        )

    def _prompt(self, request: TutorRequest, context: TutorContext) -> str:
        return (
            f"{_prompt_template()}\n\n"
            f"user_message: {request.message}\n"
            f"learner_level: {request.learner.get('level', 'beginner')}\n"
            f"current_context: {request.context.model_dump_json()}\n"
            f"retrieved_context: {_context_json(context)}"
        )


def default_tutor_factory(
    *,
    nodes: Sequence[SymbolNode],
    edges: Sequence[SymbolEdge],
    status: KbStatus,
    project_summary: ProjectSummary,
) -> LearningTutor:
    """Create the default :class:`LearningTutor` instance.

    Re-exported so ``api.py`` can build a tutor without importing
    ``LearningTutor`` directly.
    """
    return LearningTutor(
        nodes=nodes,
        edges=edges,
        status=status,
        project_summary=project_summary,
    )


def sse_encode(event: dict) -> str:
    """Encode one structured event as Server-Sent Events text."""

    return (
        f"event: {event['event']}\n"
        f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
    )


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_]+", text.lower())
        if len(token) >= 2 and token not in STOPWORDS
    }


def _prompt_template() -> str:
    try:
        return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return (
            f"Prompt version: {PROMPT_VERSION}\n"
            "Answer as a source-grounded AI tutor with citations when available."
        )


def _context_json(context: TutorContext) -> str:
    return json.dumps(
        {
            "nodes": context.graph_context["nodes"],
            "relationships": context.graph_context["relationships"],
            "citations": [citation.model_dump() for citation in context.citations],
            "warnings": [warning.model_dump() for warning in context.warnings],
        },
        ensure_ascii=False,
    )


def _token_chunks(text: str) -> Iterator[str]:
    words = text.split()
    for index in range(0, len(words), 10):
        yield " ".join(words[index : index + 10]) + (" " if index + 10 < len(words) else "")


def _dedupe_citations(citations: Iterable[Citation]) -> list[Citation]:
    seen: set[tuple[str | None, int | None, int | None, str | None]] = set()
    result: list[Citation] = []
    for citation in citations:
        key = (citation.path, citation.line_start, citation.line_end, citation.node_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(citation)
    return result


def _dedupe_warnings(warnings: Iterable[WarningInfo]) -> list[WarningInfo]:
    seen: set[str] = set()
    result: list[WarningInfo] = []
    for warning in warnings:
        if warning.code in seen:
            continue
        seen.add(warning.code)
        result.append(warning)
    return result


def _friendly_edge_label(kind: str) -> str:
    labels = {
        "calls": "calls",
        "imports": "depends on",
        "contains": "contains",
        "inherits": "extends",
        "implements": "implements",
        "uses_type": "uses",
        "bridges_to": "bridges to",
        "references_repo": "references",
    }
    return labels.get(kind, kind.replace("_", " "))


def _intent_intro(message: str, context: LearningContext) -> str:
    lowered = message.lower()
    if "first" in lowered or "start" in lowered:
        return "I would start with the smallest source-backed concept that explains the larger path."
    if "simple" in lowered or "explain" in lowered:
        return "Here is the simple version."
    if context.topic_id:
        return f"About `{context.topic_id}`:"
    return "Here is a source-grounded way to think about it."


def _summary(message: str, node_names: list[str]) -> str:
    if node_names:
        return f"Answered with context from {', '.join(node_names[:3])}."
    if message.strip():
        return "Answered with deterministic tutor fallback and no graph context."
    return "Answered a general tutor prompt."


def _key_concepts(context: TutorContext) -> list[str]:
    concepts = [node.name for node in context.nodes[:3]]
    for edge in context.relationships:
        label = _friendly_edge_label(edge.kind.value)
        if label not in concepts:
            concepts.append(label)
        if len(concepts) >= 5:
            break
    return concepts or ["architecture", "learning_path", "source_citation"]


def _suggested_questions(context: TutorContext, learning_context: LearningContext) -> list[str]:
    if context.nodes:
        primary = context.nodes[0]
        return [
            f"Can you explain {primary.name} more simply?",
            f"What should I inspect before {primary.name}?",
            f"Show an example from {primary.path}.",
        ]
    if learning_context.path_id:
        return [
            "What is the goal of this learning path?",
            "What lesson should I do next?",
            "Which source file should I inspect first?",
        ]
    return [
        "What should I learn first?",
        "Explain the architecture in simple language.",
        "Show me an important source-backed topic.",
    ]


def _next_steps(context: TutorContext) -> list[NextAction]:
    if context.nodes:
        return [
            NextAction(
                type="open_topic",
                label=f"Open {context.nodes[0].name}",
                target_id=context.nodes[0].id,
            )
        ]
    return [
        NextAction(
            type="start_path",
            label="Start with architecture",
            target_id="architecture-overview",
        )
    ]
