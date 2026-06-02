"""Topic page explanation and search helpers for the learning platform."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import re

from kb_agent.learning.citations import citation_from_node
from kb_agent.learning.models import (
    Citation,
    KbStatus,
    TopicPage,
    TopicProgress,
    TopicSearchResult,
    WarningInfo,
)
from kb_agent.models.graph import SymbolEdge, SymbolNode


PROMPT_VERSION = "topic_explainer.v1"
# TODO(Phase 7): route provider-backed topic generation through prompts/topic_explainer.v1.txt.
MAX_TOPIC_NEIGHBORS = 8
MAX_TOPIC_SEARCH_RESULTS = 20
STOPWORDS = {
    "a",
    "an",
    "and",
    "by",
    "for",
    "from",
    "in",
    "of",
    "the",
    "to",
    "with",
}


@dataclass(frozen=True)
class TopicCandidate:
    """Resolved graph node plus lightweight aliases."""

    node: SymbolNode
    aliases: set[str]


@dataclass(frozen=True)
class TopicSearchDocument:
    """Precomputed searchable fields for a topic candidate."""

    candidate: TopicCandidate
    name: str
    path: str
    kind: str
    signature: str
    aliases: set[str]
    tokens_by_field: dict[str, set[str]]


class TopicExplainer:
    """Build learner-friendly topic pages from graph nodes and edges."""

    def __init__(
        self,
        *,
        nodes: Sequence[SymbolNode],
        edges: Sequence[SymbolEdge],
        status: KbStatus,
    ) -> None:
        self.nodes = list(nodes)
        self.edges = list(edges)
        self.status = status
        self.node_by_id = {node.id: node for node in self.nodes}
        self.candidates = [_candidate(node) for node in self.nodes]
        self.alias_index = _alias_index(self.candidates)
        (
            self.search_documents,
            self.token_index,
            self.prefix_index,
            self.ngram_index,
        ) = _build_search_indexes(self.candidates)

    def explain(
        self,
        topic_id: str,
        *,
        progress: TopicProgress | None = None,
        cached: dict | None = None,
    ) -> TopicPage:
        """Return a topic page for a graph node or a structured not-found response."""

        node = self.resolve(topic_id)
        if node is None:
            warnings = list(self.status.warnings)
            warnings.append(
                WarningInfo(
                    code="topic_not_found",
                    message="Topic was not found in the current graph.",
                )
            )
            return TopicPage(
                id=topic_id,
                type="unknown",
                title=topic_id,
                summary="Topic not found.",
                explanation="This topic is not available in the current knowledge graph.",
                why_it_matters="Generate or refresh the knowledge base to make this topic available.",
                progress=progress or TopicProgress(),
                warnings=_dedupe_warnings(warnings),
            )

        if cached:
            try:
                page = TopicPage.model_validate(cached)
                return page.model_copy(update={"progress": progress or page.progress})
            except Exception:
                pass

        incoming, outgoing = self._relationships_for(node.id)
        related_nodes = self._related_nodes(incoming, outgoing, node.id)
        citations = _dedupe_citations([citation_from_node(node)])
        warnings = list(self.status.warnings)
        if not citations:
            warnings.append(
                WarningInfo(
                    code="missing_citations",
                    message="No source citation is available for this topic.",
                )
            )

        return TopicPage(
            id=node.id,
            type=node.kind.value,
            title=node.name,
            summary=_summary(node),
            explanation=_explanation(node, related_nodes, incoming, outgoing),
            why_it_matters=_why_it_matters(node, incoming, outgoing),
            examples=_examples(node),
            prerequisites=_prerequisites(incoming, self.node_by_id),
            related_topics=[related.id for related in related_nodes[:6]],
            related_symbols=[related.name for related in related_nodes[:6]],
            citations=citations,
            progress=progress or TopicProgress(),
            suggested_questions=_suggested_questions(node, related_nodes),
            graph_context={
                "nodes": _graph_nodes([node, *related_nodes[:MAX_TOPIC_NEIGHBORS]]),
                "relationships": _graph_relationships(
                    [*outgoing, *incoming],
                    self.node_by_id,
                    limit=MAX_TOPIC_NEIGHBORS,
                ),
            },
            warnings=_dedupe_warnings(warnings),
        )

    def search(self, query: str) -> list[TopicSearchResult]:
        """Search topics by title, path, kind, signature, and aliases.

        The explainer builds a small inverted index once at construction time,
        then scores only matching candidate documents. This keeps query latency
        bounded by the number of likely matches instead of the full graph size.
        """

        q = query.strip().lower()
        if not q:
            return []
        tokens = _tokens(q)
        candidate_ids = self._search_candidate_ids(q, tokens)
        if not candidate_ids:
            return []

        results: list[TopicSearchResult] = []
        for candidate_id in candidate_ids:
            document = self.search_documents[candidate_id]
            node = document.candidate.node
            matched_fields: list[str] = []
            score = 0.0

            if q == document.name:
                score += 1.2
                matched_fields.append("title")
            elif q in document.name or tokens & document.tokens_by_field["title"]:
                score += 1.0
                matched_fields.append("title")
            if q in document.path or tokens & document.tokens_by_field["summary"]:
                score += 0.55
                matched_fields.append("summary")
            if q in document.kind or tokens & document.tokens_by_field["type"]:
                score += 0.35
                matched_fields.append("type")
            if document.signature and (q in document.signature or tokens & document.tokens_by_field["signature"]):
                score += 0.3
                matched_fields.append("signature")
            if any(q in alias for alias in document.aliases):
                score += 0.25
                matched_fields.append("alias")

            if score > 0:
                results.append(
                    TopicSearchResult(
                        id=node.id,
                        type=node.kind.value,
                        title=node.name,
                        summary=_summary(node),
                        score=round(min(score, 1.0), 3),
                        matched_fields=_unique(matched_fields),
                    )
                )

        results.sort(key=lambda item: (-item.score, item.title.lower(), item.id))
        return results[:MAX_TOPIC_SEARCH_RESULTS]

    def _search_candidate_ids(self, query: str, tokens: set[str]) -> set[int]:
        candidate_ids: set[int] = set()
        alias_match = self.alias_index.get(query)
        if alias_match is not None:
            candidate_ids.add(alias_match)

        for token in tokens:
            candidate_ids.update(self.token_index.get(token, set()))
            candidate_ids.update(self.prefix_index.get(token, set()))

        if query:
            candidate_ids.update(self.token_index.get(query, set()))
            candidate_ids.update(self.prefix_index.get(query, set()))
        if len(query) >= 3:
            gram_matches = [
                self.ngram_index.get(gram, set())
                for gram in _ngrams(query)
            ]
            gram_matches = [matches for matches in gram_matches if matches]
            if gram_matches:
                candidate_ids.update(set.intersection(*gram_matches))
        return candidate_ids

    def resolve(self, topic_id: str) -> SymbolNode | None:
        """Resolve a topic by exact id, name, path/name alias, or URL-safe id."""

        normalized = topic_id.strip()
        if normalized in self.node_by_id:
            return self.node_by_id[normalized]
        normalized_lower = normalized.lower()
        candidate_id = self.alias_index.get(normalized_lower)
        if candidate_id is not None:
            return self.search_documents[candidate_id].candidate.node
        return None

    def _relationships_for(self, node_id: str) -> tuple[list[SymbolEdge], list[SymbolEdge]]:
        incoming = [edge for edge in self.edges if edge.target == node_id]
        outgoing = [edge for edge in self.edges if edge.source == node_id]
        incoming.sort(key=lambda edge: (-edge.confidence, edge.kind.value, edge.source))
        outgoing.sort(key=lambda edge: (-edge.confidence, edge.kind.value, edge.target))
        return incoming[:MAX_TOPIC_NEIGHBORS], outgoing[:MAX_TOPIC_NEIGHBORS]

    def _related_nodes(
        self,
        incoming: Sequence[SymbolEdge],
        outgoing: Sequence[SymbolEdge],
        node_id: str,
    ) -> list[SymbolNode]:
        related: list[SymbolNode] = []
        for edge in [*outgoing, *incoming]:
            other_id = edge.target if edge.source == node_id else edge.source
            other = self.node_by_id.get(other_id)
            if other is not None and other.id != node_id:
                related.append(other)
        return _unique_nodes(related)


def cache_payload(page: TopicPage) -> dict:
    """Return the stable generated portion of a topic page for persistence."""

    payload = page.model_dump()
    payload["progress"] = TopicProgress().model_dump()
    payload["metadata"] = {"prompt_version": PROMPT_VERSION}
    return payload


def _candidate(node: SymbolNode) -> TopicCandidate:
    aliases = {
        node.id.lower(),
        node.name.lower(),
        node.path.lower(),
        f"{node.path}::{node.name}".lower(),
        _slug(node.name),
        _slug(node.id),
        _slug(f"{node.path}-{node.name}"),
    }
    return TopicCandidate(node=node, aliases=aliases)


def _alias_index(candidates: Sequence[TopicCandidate]) -> dict[str, int]:
    index: dict[str, int] = {}
    for candidate_id, candidate in enumerate(candidates):
        for alias in candidate.aliases:
            index.setdefault(alias, candidate_id)
    return index


def _build_search_indexes(
    candidates: Sequence[TopicCandidate],
) -> tuple[
    list[TopicSearchDocument],
    dict[str, set[int]],
    dict[str, set[int]],
    dict[str, set[int]],
]:
    documents = [_search_document(candidate) for candidate in candidates]
    token_index: dict[str, set[int]] = defaultdict(set)
    prefix_index: dict[str, set[int]] = defaultdict(set)
    ngram_index: dict[str, set[int]] = defaultdict(set)

    for candidate_id, document in enumerate(documents):
        searchable_text = " ".join([
            document.name,
            document.path,
            document.kind,
            document.signature,
            *document.aliases,
        ])
        all_tokens = set().union(*document.tokens_by_field.values())
        for token in all_tokens:
            token_index[token].add(candidate_id)
            for prefix in _prefixes(token):
                prefix_index[prefix].add(candidate_id)
        for gram in _ngrams(searchable_text):
            ngram_index[gram].add(candidate_id)

    return documents, dict(token_index), dict(prefix_index), dict(ngram_index)


def _search_document(candidate: TopicCandidate) -> TopicSearchDocument:
    node = candidate.node
    name = node.name.lower()
    path = node.path.lower()
    kind = node.kind.value.lower()
    signature = (node.signature or "").lower()
    aliases = {alias.lower() for alias in candidate.aliases}
    return TopicSearchDocument(
        candidate=candidate,
        name=name,
        path=path,
        kind=kind,
        signature=signature,
        aliases=aliases,
        tokens_by_field={
            "title": _tokens(name),
            "summary": _tokens(path),
            "type": _tokens(kind),
            "signature": _tokens(signature),
            "alias": set().union(*(_tokens(alias) for alias in aliases)) if aliases else set(),
        },
    )


def _summary(node: SymbolNode) -> str:
    return f"{node.name} is a {node.kind.value} defined in {node.path}."


def _explanation(
    node: SymbolNode,
    related_nodes: Sequence[SymbolNode],
    incoming: Sequence[SymbolEdge],
    outgoing: Sequence[SymbolEdge],
) -> str:
    parts = [
        (
            f"{node.name} is a source-backed {node.kind.value}. Read it first as a named "
            f"unit in {node.path}, then connect it to the surrounding calls and dependencies."
        )
    ]
    if node.docstring:
        parts.append(f"The source documentation says: {node.docstring.strip()}")
    if node.signature:
        parts.append(f"Its signature gives the quickest shape of the API: {node.signature}")
    if outgoing:
        labels = _relationship_labels(outgoing)
        parts.append(f"From this topic, the graph points outward through {', '.join(labels)}.")
    if incoming:
        labels = _relationship_labels(incoming)
        parts.append(f"Other code reaches this topic through {', '.join(labels)}.")
    if related_nodes:
        names = ", ".join(node.name for node in related_nodes[:4])
        parts.append(f"Keep nearby topics in view: {names}.")
    return " ".join(parts)


def _why_it_matters(
    node: SymbolNode,
    incoming: Sequence[SymbolEdge],
    outgoing: Sequence[SymbolEdge],
) -> str:
    if incoming and outgoing:
        return (
            "It sits between callers and downstream behavior, so it is useful for tracing both "
            "how control reaches this point and what changes might affect next."
        )
    if incoming:
        return "Other symbols depend on it, which makes it a useful place to understand impact."
    if outgoing:
        return "It leads to other symbols, which makes it a practical starting point for following behavior."
    return "It is a named source symbol, so it can anchor tutor answers, citations, and later learning paths."


def _examples(node: SymbolNode) -> list[str]:
    examples = []
    if node.signature:
        examples.append(node.signature)
    if node.docstring:
        examples.append(node.docstring.strip())
    return examples


def _prerequisites(incoming: Sequence[SymbolEdge], node_by_id: dict[str, SymbolNode]) -> list[str]:
    prereqs = []
    for edge in incoming:
        if edge.kind.value in {"contains", "imports", "uses_type", "inherits", "implements"}:
            source = node_by_id.get(edge.source)
            if source is not None:
                prereqs.append(source.id)
    return _unique(prereqs)[:5]


def _suggested_questions(node: SymbolNode, related_nodes: Sequence[SymbolNode]) -> list[str]:
    questions = [
        f"Can you explain {node.name} more simply?",
        f"What should I know before {node.name}?",
        f"Show me the source context for {node.name}.",
    ]
    if related_nodes:
        questions.append(f"How is {node.name} connected to {related_nodes[0].name}?")
    return questions[:4]


def _graph_nodes(nodes: Sequence[SymbolNode]) -> list[dict]:
    return [
        {
            "id": node.id,
            "name": node.name,
            "kind": node.kind.value,
            "path": node.path,
            "line_start": node.line_start,
            "line_end": node.line_end,
        }
        for node in _unique_nodes(nodes)
    ]


def _graph_relationships(
    edges: Sequence[SymbolEdge],
    node_by_id: dict[str, SymbolNode],
    *,
    limit: int,
) -> list[dict]:
    return [
        {
            "source": edge.source,
            "source_name": getattr(node_by_id.get(edge.source), "name", edge.source),
            "target": edge.target,
            "target_name": getattr(node_by_id.get(edge.target), "name", edge.target),
            "kind": _friendly_edge_label(edge.kind.value),
            "confidence": edge.confidence,
        }
        for edge in edges[:limit]
    ]


def _relationship_labels(edges: Sequence[SymbolEdge]) -> list[str]:
    return _unique(_friendly_edge_label(edge.kind.value) for edge in edges)


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


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_]+", text.lower())
        if len(token) >= 2 and token not in STOPWORDS
    }


def _prefixes(token: str) -> set[str]:
    return {
        token[:index]
        for index in range(2, len(token) + 1)
    }


def _ngrams(text: str, size: int = 3) -> set[str]:
    normalized = re.sub(r"\s+", " ", text.lower())
    if len(normalized) < size:
        return set()
    return {
        normalized[index : index + size]
        for index in range(0, len(normalized) - size + 1)
    }


def _slug(value: str) -> str:
    tokens = [
        token
        for token in re.findall(r"[a-zA-Z0-9_]+", value.lower())
        if len(token) >= 2 and token not in STOPWORDS
    ]
    return "-".join(tokens) or value.lower().replace(" ", "-")


def _unique(items: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _unique_nodes(nodes: Sequence[SymbolNode]) -> list[SymbolNode]:
    seen = set()
    result = []
    for node in nodes:
        if node.id in seen:
            continue
        seen.add(node.id)
        result.append(node)
    return result


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
