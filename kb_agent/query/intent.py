"""Query intent classification using keyword matching."""
from __future__ import annotations

from enum import Enum


class QueryIntent(str, Enum):
    SYMBOL_LOOKUP = "symbol_lookup"
    FLOW_TRACE = "flow_trace"
    MODULE_OVERVIEW = "module_overview"
    RELATIONSHIP = "relationship"
    DEFAULT = "default"


INTENT_BUDGET_RATIOS: dict[QueryIntent, dict[str, float]] = {
    QueryIntent.SYMBOL_LOOKUP: {"entry": 0.60, "hop1": 0.20, "hop2": 0.10, "hop3": 0.00, "meta": 0.10},
    QueryIntent.FLOW_TRACE: {"entry": 0.25, "hop1": 0.40, "hop2": 0.20, "hop3": 0.05, "meta": 0.10},
    QueryIntent.MODULE_OVERVIEW: {"entry": 0.30, "hop1": 0.40, "hop2": 0.20, "hop3": 0.00, "meta": 0.10},
    QueryIntent.RELATIONSHIP: {"entry": 0.30, "hop1": 0.40, "hop2": 0.20, "hop3": 0.00, "meta": 0.10},
    QueryIntent.DEFAULT: {"entry": 0.40, "hop1": 0.35, "hop2": 0.15, "hop3": 0.00, "meta": 0.10},
}

_INTENT_KEYWORDS: dict[QueryIntent, list[str]] = {
    QueryIntent.SYMBOL_LOOKUP: [
        "what does", "what is", "explain", "describe", "tell me about",
        "show me", "definition of",
    ],
    QueryIntent.FLOW_TRACE: [
        "how does", "how do", "flow", "process", "trace", "sequence",
        "step by step", "execution path", "call chain",
    ],
    QueryIntent.MODULE_OVERVIEW: [
        "what's in", "overview", "contents of", "what are the",
        "all classes", "all functions",
    ],
    QueryIntent.RELATIONSHIP: [
        "what uses", "depends on", "callers of", "who calls",
        "references", "imported by", "depends",
    ],
}


def classify_intent(query: str) -> QueryIntent:
    """Classify query intent by keyword matching.

    Checks in specificity order — more specific patterns first to avoid
    premature matches (e.g. "what uses" → RELATIONSHIP, not SYMBOL_LOOKUP).
    """
    lower = query.lower().strip()
    for intent in [
        QueryIntent.RELATIONSHIP,
        QueryIntent.FLOW_TRACE,
        QueryIntent.MODULE_OVERVIEW,
        QueryIntent.SYMBOL_LOOKUP,
    ]:
        for kw in _INTENT_KEYWORDS[intent]:
            if kw in lower:
                return intent
    return QueryIntent.DEFAULT
