"""Context composition with adaptive token budget."""
from __future__ import annotations

from dataclasses import dataclass, field

from kb_agent.models.entry import KBEntry
from kb_agent.models.graph import SymbolEdge
from kb_agent.query.expander import ExpandedSubgraph
from kb_agent.query.intent import INTENT_BUDGET_RATIOS, QueryIntent

TOTAL_TOKEN_BUDGET = 4000
PER_NODE_TOKEN_CAP = 500
CHARS_PER_TOKEN = 4


@dataclass
class RetrievalMetrics:
    query: str
    intent: str
    seed_nodes: list[str]
    expanded_nodes: list[str]
    relationship_edges: list[tuple[str, str, str]]
    token_allocation: dict[str, int]
    truncated: bool
    truncated_nodes: list[str]
    total_tokens_used: int


@dataclass
class RetrievalResult:
    context: str
    entries: list[KBEntry]
    metrics: RetrievalMetrics


def compose_context(
    subgraph: ExpandedSubgraph,
    seed_entries: list[KBEntry],
    unmapped_entries: list[KBEntry],
    intent: QueryIntent,
) -> RetrievalResult:
    """Compose structured context from expanded subgraph."""
    ratios = INTENT_BUDGET_RATIOS[intent]
    budgets = {tier: int(TOTAL_TOKEN_BUDGET * r) for tier, r in ratios.items()}

    entry_lookup = _build_entry_lookup(seed_entries)
    sections: list[str] = []
    allocation: dict[str, int] = {"entry": 0, "hop1": 0, "hop2": 0, "meta": 0}
    truncated_nodes: list[str] = []
    total_tokens = 0

    # Seed tier — full detail
    seed_text, seed_tok, seed_trunc = _format_tier(
        subgraph.seed_nodes, entry_lookup, budgets["entry"], "full",
    )
    if seed_text:
        sections.append(f"=== PRIMARY RESULTS ===\n{seed_text}")
    allocation["entry"] = seed_tok
    truncated_nodes.extend(seed_trunc)
    total_tokens += seed_tok

    # 1-hop tier — summary
    hop1_text, hop1_tok, hop1_trunc = _format_tier(
        subgraph.hop1_nodes, entry_lookup, budgets["hop1"], "summary",
    )
    if hop1_text:
        sections.append(f"=== RELATED (1-hop) ===\n{hop1_text}")
    allocation["hop1"] = hop1_tok
    truncated_nodes.extend(hop1_trunc)
    total_tokens += hop1_tok

    # 2-hop tier — minimal
    hop2_text, hop2_tok, hop2_trunc = _format_tier(
        subgraph.hop2_nodes, entry_lookup, budgets["hop2"], "minimal",
    )
    if hop2_text:
        sections.append(f"=== CONTEXT (2-hop) ===\n{hop2_text}")
    allocation["hop2"] = hop2_tok
    truncated_nodes.extend(hop2_trunc)
    total_tokens += hop2_tok

    # Meta tier — arch/mod/file entries
    meta_text, meta_tok = _format_meta(unmapped_entries, budgets["meta"])
    if meta_text:
        sections.append(f"=== METADATA ===\n{meta_text}")
    allocation["meta"] = meta_tok
    total_tokens += meta_tok

    # Edge summary — bounded by remaining token budget
    remaining = TOTAL_TOKEN_BUDGET - total_tokens
    edge_text = _format_edges(subgraph.relevant_edges)
    edge_tok = 0
    if edge_text and remaining > 0:
        edge_section = f"=== RELATIONSHIPS ===\n{edge_text}"
        edge_tok = _estimate_tokens(edge_section)
        if edge_tok > remaining:
            edge_section = _truncate_edges(edge_text, remaining)
            edge_tok = _estimate_tokens(edge_section)
        sections.append(edge_section)
    total_tokens += edge_tok

    all_node_ids = [n.id for n in subgraph.all_nodes]
    # Deduplicate: unmapped_entries is a subset of seed_entries, use a set
    seen_ids: set[str] = set()
    unique_entries: list[KBEntry] = []
    for e in seed_entries:
        if e.id not in seen_ids:
            unique_entries.append(e)
            seen_ids.add(e.id)
    for e in unmapped_entries:
        if e.id not in seen_ids:
            unique_entries.append(e)
            seen_ids.add(e.id)

    return RetrievalResult(
        context="\n\n".join(sections),
        entries=unique_entries,
        metrics=RetrievalMetrics(
            query="",
            intent=intent.value,
            seed_nodes=[n.id for n in subgraph.seed_nodes],
            expanded_nodes=all_node_ids,
            relationship_edges=[
                (edge.source, edge.target, edge.kind.value)
                for edge in subgraph.relevant_edges
            ],
            token_allocation=allocation,
            truncated=len(truncated_nodes) > 0,
            truncated_nodes=truncated_nodes,
            total_tokens_used=total_tokens,
        ),
    )


def _build_entry_lookup(
    entries: list[KBEntry],
) -> dict[tuple[str, int], KBEntry]:
    return {(e.static.path, e.static.line_start): e for e in entries if e.layer.value == "mem"}


def _format_tier(
    nodes: list[SymbolNode],
    entry_lookup: dict[tuple[str, int], KBEntry],
    budget: int,
    detail: str,
) -> tuple[str, int, list[str]]:
    """Format a tier of nodes within token budget.

    Returns (text, tokens_used, truncated_node_ids).
    """
    lines: list[str] = []
    tokens_used = 0
    truncated: list[str] = []

    for node in nodes:
        entry = entry_lookup.get((node.path, node.line_start))
        text = _format_node(node, entry, detail)
        node_tokens = _estimate_tokens(text)

        if node_tokens > PER_NODE_TOKEN_CAP:
            text = _truncate_node(node, detail)
            node_tokens = _estimate_tokens(text)
            truncated.append(node.id)

        if tokens_used + node_tokens > budget and tokens_used > 0:
            truncated.append(node.id)
            continue

        lines.append(text)
        tokens_used += node_tokens

    return "\n".join(lines), tokens_used, truncated


def _format_node(node: SymbolNode, entry: KBEntry | None, detail: str) -> str:
    parts: list[str] = [f"[{node.kind.value}] {node.name}"]
    if detail == "full":
        if node.signature:
            parts.append(f"  Signature: {node.signature}")
        if node.return_type:
            parts.append(f"  Returns: {node.return_type}")
        if entry and entry.ai.summary:
            parts.append(f"  Summary: {entry.ai.summary}")
        if node.docstring:
            parts.append(f"  Docstring: {node.docstring}")
        parts.append(f"  Location: {node.path}:{node.line_start}")
    elif detail == "summary":
        if node.signature:
            parts.append(f"  Signature: {node.signature}")
        if entry and entry.ai.summary:
            parts.append(f"  Summary: {entry.ai.summary}")
        parts.append(f"  Location: {node.path}:{node.line_start}")
    else:  # minimal
        parts.append(f"  Location: {node.path}:{node.line_start}")
    return "\n".join(parts)


def _truncate_node(node: SymbolNode, detail: str) -> str:
    """Truncate node representation — always keep name + kind + signature."""
    parts = [f"[{node.kind.value}] {node.name}"]
    if node.signature:
        parts.append(f"  Signature: {node.signature}")
    parts.append(f"  Location: {node.path}:{node.line_start}")
    return "\n".join(parts)


def _format_meta(
    entries: list[KBEntry], budget: int,
) -> tuple[str, int]:
    if not entries:
        return "", 0
    lines: list[str] = []
    tokens = 0
    for entry in entries:
        text = f"[{entry.layer.value}] {entry.id}"
        if entry.ai.summary:
            text += f"\n  {entry.ai.summary}"
        t = _estimate_tokens(text)
        if tokens + t > budget:
            break
        lines.append(text)
        tokens += t
    return "\n".join(lines), tokens


def _format_edges(edges: list[SymbolEdge]) -> str:
    if not edges:
        return ""
    lines: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for e in edges:
        key = (e.source, e.target, e.kind.value)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{_short_id(e.source)} --{e.kind.value}--> {_short_id(e.target)} (conf: {e.confidence:.2f})")
    return "\n".join(lines)


def _short_id(node_id: str) -> str:
    """Show last two segments of node ID for readability."""
    parts = node_id.split("::")
    if len(parts) >= 2:
        return f"{parts[-2].split('/')[-1]}::{parts[-1]}"
    return node_id


def _truncate_edges(edge_text: str, budget: int) -> str:
    """Truncate edge section to fit within remaining token budget."""
    header = "=== RELATIONSHIPS ===\n"
    header_tok = _estimate_tokens(header)
    lines = edge_text.split("\n")
    kept: list[str] = []
    used = header_tok
    for line in lines:
        line_tok = _estimate_tokens(line)
        if used + line_tok > budget:
            break
        kept.append(line)
        used += line_tok
    if not kept:
        return ""
    return header + "\n".join(kept)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)
