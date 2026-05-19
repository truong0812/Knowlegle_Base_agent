"""Query intent classification using keyword matching."""
from __future__ import annotations

from enum import Enum


class QueryIntent(str, Enum):
    SYMBOL_LOOKUP = "symbol_lookup"
    FLOW_TRACE = "flow_trace"
    CHAIN_TRACE = "chain_trace"
    MODULE_OVERVIEW = "module_overview"
    RELATIONSHIP = "relationship"
    VERSION_DIFF = "version_diff"
    DEFAULT = "default"


INTENT_BUDGET_RATIOS: dict[QueryIntent, dict[str, float]] = {
    QueryIntent.SYMBOL_LOOKUP: {"entry": 0.60, "hop1": 0.20, "hop2": 0.10, "hop3": 0.00, "meta": 0.10},
    QueryIntent.FLOW_TRACE: {"entry": 0.25, "hop1": 0.40, "hop2": 0.20, "hop3": 0.05, "meta": 0.10},
    QueryIntent.CHAIN_TRACE: {"entry": 0.10, "hop1": 0.20, "hop2": 0.15, "hop3": 0.10, "hop4": 0.10, "chain": 0.25, "meta": 0.10},
    QueryIntent.MODULE_OVERVIEW: {"entry": 0.30, "hop1": 0.40, "hop2": 0.20, "hop3": 0.00, "meta": 0.10},
    QueryIntent.RELATIONSHIP: {"entry": 0.30, "hop1": 0.40, "hop2": 0.20, "hop3": 0.00, "meta": 0.10},
    QueryIntent.VERSION_DIFF: {"entry": 0.40, "hop1": 0.30, "hop2": 0.20, "hop3": 0.00, "meta": 0.10},
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
    QueryIntent.VERSION_DIFF: [
        "what changed", "changes since", "diff since", "what's new",
        "what was added", "what was removed", "recently modified",
        "what changed since",
    ],
    QueryIntent.CHAIN_TRACE: [
        "call chain", "causal chain", "execution chain",
        "end to end", "full path from", "trace from",
        "call sequence from",
    ],
}


def classify_intent(query: str) -> QueryIntent:
    """Classify query intent by keyword matching.

    Checks in specificity order — more specific patterns first to avoid
    premature matches (e.g. "what uses" → RELATIONSHIP, not SYMBOL_LOOKUP).
    """
    lower = query.lower().strip()
    for intent in [
        QueryIntent.VERSION_DIFF,
        QueryIntent.CHAIN_TRACE,
        QueryIntent.RELATIONSHIP,
        QueryIntent.FLOW_TRACE,
        QueryIntent.MODULE_OVERVIEW,
        QueryIntent.SYMBOL_LOOKUP,
    ]:
        for kw in _INTENT_KEYWORDS[intent]:
            if kw in lower:
                return intent
    return QueryIntent.DEFAULT
