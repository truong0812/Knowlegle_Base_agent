"""Chat backend — intent router + KB-backed answer generation."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatContext(BaseModel):
    active_view: str | None = None
    node_id: str | None = None
    feature_id: str | None = None
    file_path: str | None = None


class ChatRequest(BaseModel):
    question: str
    context: ChatContext = Field(default_factory=ChatContext)
    history: list[dict] = Field(default_factory=list)


class Citation(BaseModel):
    label: str
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    node_id: str | None = None


class ChatError(BaseModel):
    code: str
    message: str


class ChatResponse(BaseModel):
    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    error: ChatError | None = None


# ---------------------------------------------------------------------------
# Intent patterns (VI + EN)
# ---------------------------------------------------------------------------

_INTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("callers", re.compile(
        r"(ai\s*g[oọ]\w*|who\s*call|callers|call.*by|được\s*gọi)",
        re.IGNORECASE,
    )),
    ("callees", re.compile(
        r"(g[oọ]\w*\s*g[ìi]|callees|calls\s*what|call.*to)",
        re.IGNORECASE,
    )),
    ("impact", re.compile(
        r"(ả?nh\s*hưởng|impact|thay\s*đổi|chang|affect|sửa|nếu\s*sửa)",
        re.IGNORECASE,
    )),
    ("explain", re.compile(
        r"(giải\s*thích|explain|làm\s*g[ìi]|what.*do| là gì|what is)",
        re.IGNORECASE,
    )),
]


# ---------------------------------------------------------------------------
# Suggested questions
# ---------------------------------------------------------------------------

_SUGGESTIONS: dict[str | None, list[str]] = {
    None: [
        "Repo này làm gì?",
        "Tôi nên học module nào trước?",
        "Các flow chính của dự án là gì?",
        "Những phần nào quan trọng nhất?",
    ],
    "overview": [
        "Repo này làm gì?",
        "Tôi nên học module nào trước?",
        "Các flow chính của dự án là gì?",
        "Những phần nào quan trọng nhất?",
    ],
    "features": [
        "Feature này giải quyết vấn đề gì?",
        "Các symbol quan trọng nhất là gì?",
        "Feature này phụ thuộc vào module nào?",
    ],
    "node": [
        "Function/class này làm gì?",
        "Ai gọi nó?",
        "Nó gọi những gì?",
        "Nếu sửa nó thì ảnh hưởng gì?",
        "Tôi nên đọc file nào tiếp?",
    ],
    "graph": [
        "Cấu trúc tổng thể của dự án như thế nào?",
        "Module nào quan trọng nhất?",
        "Các kết nối chính giữa các module?",
    ],
}


# ---------------------------------------------------------------------------
# ChatHandler
# ---------------------------------------------------------------------------

class ChatHandler:
    """Rule-based intent router + KB-backed answer generator."""

    def __init__(self, kb_dir: Path) -> None:
        self._kb_dir = kb_dir.resolve()
        self._tools: "KBTools | None" = None  # lazy
        self._llm_available: bool = bool(os.environ.get("OPENAI_API_KEY"))

    # -- lazy helpers --

    def _get_tools(self) -> "KBTools":
        if self._tools is None:
            from kb_agent.mcp_server.tools import KBTools
            self._tools = KBTools(self._kb_dir)
        return self._tools

    def _kb_exists(self) -> bool:
        return (self._kb_dir / "manifest.json").exists()

    # -- public API --

    def handle(self, request: ChatRequest) -> ChatResponse:
        """Process a chat request and return a response."""
        # 1. Check KB exists
        if not self._kb_exists():
            return ChatResponse(
                error=ChatError(
                    code="missing_kb",
                    message=".kb/ not found. Run analyze first.",
                ),
            )

        # 2. Resolve node_id
        node_id = request.context.node_id
        if node_id:
            tools = self._get_tools()
            resolved = tools._resolve_node(node_id)
            if resolved:
                node_id = resolved
            # keep original if not resolved — tools will report "not found"

        # 3. Route intent
        intent = self._route_intent(request.question, node_id)

        # 4. Execute tool call
        answer_text, citations = self._execute_intent(intent, request.question, node_id)

        # 5. LLM enhancement (optional)
        if self._llm_available:
            answer_text = self._try_llm(request.question, answer_text, node_id) or answer_text

        # 6. Suggestions
        suggestions = self._suggest_questions(request.context.active_view, node_id)

        return ChatResponse(
            answer=answer_text,
            citations=citations,
            suggested_questions=suggestions,
        )

    # -- intent routing --

    def _route_intent(self, question: str, node_id: str | None) -> str:
        """Return intent name based on question patterns and context."""
        if not node_id:
            return "general"

        for intent_name, pattern in _INTENT_PATTERNS:
            if pattern.search(question):
                return intent_name

        # Has node_id but no specific pattern → explain
        return "explain"

    # -- tool execution --

    def _execute_intent(
        self,
        intent: str,
        question: str,
        node_id: str | None,
    ) -> tuple[str, list[Citation]]:
        """Execute the right KB tool and return (answer_text, citations)."""
        tools = self._get_tools()

        if intent == "callers" and node_id:
            raw = tools.kb_callers(node_id)
            return raw, self._citations_from_edges(raw, node_id, "incoming")

        if intent == "callees" and node_id:
            raw = tools.kb_callees(node_id)
            return raw, self._citations_from_edges(raw, node_id, "outgoing")

        if intent == "impact" and node_id:
            raw = tools.kb_impact(node_id)
            return raw, self._citations_from_node(node_id)

        if intent == "explain" and node_id:
            raw = tools.kb_node(node_id)
            node_citations = self._citations_from_node(node_id)
            # Also try retrieval for richer context
            retrieval_citations = self._try_retrieval_citations(question)
            return raw, node_citations + retrieval_citations

        # general — retrieval-based
        answer = self._general_answer(question)
        citations = self._try_retrieval_citations(question)
        return answer, citations

    # -- answer helpers --

    def _general_answer(self, question: str) -> str:
        """Try retrieval engine, fall back to status."""
        try:
            from kb_agent.query.retrieval import RetrievalEngine
            engine = RetrievalEngine(self._kb_dir)
            result = engine.retrieve(question)
            if result.context:
                return result.context
        except (FileNotFoundError, ImportError):
            pass

        # Fallback: return KB status as context
        tools = self._get_tools()
        return tools.kb_status()

    # -- citation extraction --

    def _citations_from_node(self, node_id: str) -> list[Citation]:
        """Create citations from a known node."""
        tools = self._get_tools()
        mapper = tools._ensure_loaded()
        node = mapper.node_by_id.get(node_id)
        if not node:
            return []
        return [
            Citation(
                label=node.name,
                path=node.path,
                line_start=node.line_start,
                line_end=node.line_end,
                node_id=node_id,
            ),
        ]

    def _citations_from_edges(
        self,
        raw_output: str,
        node_id: str,
        direction: str,
    ) -> list[Citation]:
        """Parse KBTools output to extract cited nodes."""
        tools = self._get_tools()
        mapper = tools._ensure_loaded()
        citations: list[Citation] = []

        # Always include the queried node
        node = mapper.node_by_id.get(node_id)
        if node:
            citations.append(
                Citation(
                    label=node.name,
                    path=node.path,
                    line_start=node.line_start,
                    line_end=node.line_end,
                    node_id=node_id,
                ),
            )

        # Parse output for other node names
        # KBTools format: "  name --kind--> target"
        for line in raw_output.splitlines():
            line = line.strip()
            if not line or line.startswith("Callers") or line.startswith("Callees") or line.startswith("No "):
                continue
            # Try to find names in the output
            for nid, n in mapper.node_by_id.items():
                if n.name in line and nid != node_id:
                    # Avoid duplicates
                    if not any(c.node_id == nid for c in citations):
                        citations.append(
                            Citation(
                                label=n.name,
                                path=n.path,
                                line_start=n.line_start,
                                line_end=n.line_end,
                                node_id=nid,
                            ),
                        )

        return citations

    def _try_retrieval_citations(self, question: str) -> list[Citation]:
        """Try to get citations from retrieval results."""
        try:
            from kb_agent.query.retrieval import RetrievalEngine
            engine = RetrievalEngine(self._kb_dir)
            result = engine.retrieve(question)
            citations: list[Citation] = []
            for entry in result.entries[:5]:
                citations.append(
                    Citation(
                        label=entry.static.signature or entry.id,
                        path=entry.static.path,
                        line_start=entry.static.line_start,
                        line_end=entry.static.line_end,
                        node_id=entry.id,
                    ),
                )
            return citations
        except (FileNotFoundError, ImportError):
            return []

    # -- LLM integration --

    def _try_llm(
        self,
        question: str,
        context: str,
        node_id: str | None,
    ) -> str | None:
        """Try LLM-enhanced answer. Returns None on failure."""
        try:
            from kb_agent.analyzer.llm import LLMClient
            client = LLMClient()
            prompt = self._build_llm_prompt(question, context, node_id)
            # LLMClient.complete is async — for sync endpoint use, run in event loop
            import asyncio
            answer = asyncio.get_event_loop().run_until_complete(
                client.complete(prompt),
            )
            return answer
        except Exception:
            logger.warning("LLM call failed, falling back to deterministic mode", exc_info=True)
            return None

    def _build_llm_prompt(self, question: str, context: str, node_id: str | None) -> str:
        """Build a prompt for the LLM."""
        parts = [
            "You are a code learning assistant. Answer the user's question based on the provided context.",
            f"\nContext:\n{context}",
        ]
        if node_id:
            parts.append(f"\nCurrent symbol: {node_id}")
        parts.append(f"\nQuestion: {question}")
        parts.append("\nAnswer concisely in the same language as the question.")
        return "\n".join(parts)

    # -- suggested questions --

    def _suggest_questions(
        self,
        active_view: str | None,
        node_id: str | None,
    ) -> list[str]:
        """Return context-aware suggested questions."""
        base = _SUGGESTIONS.get(active_view, _SUGGESTIONS[None])
        suggestions = list(base)

        # Add node-specific suggestions if we have a node
        if node_id:
            tools = self._get_tools()
            mapper = tools._ensure_loaded()
            node = mapper.node_by_id.get(node_id)
            if node:
                name = node.name
                suggestions = [
                    f"{name} làm gì?",
                    f"Ai gọi {name}?",
                    f"{name} gọi những gì?",
                    f"Ảnh hưởng nếu sửa {name}?",
                ] + suggestions

        return suggestions[:6]
