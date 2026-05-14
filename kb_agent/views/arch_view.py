from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from kb_agent.analyzer.llm import LLMClient
from kb_agent.models.entry import AIData, KBEntry, Language, Layer, StaticData, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode

from .base import ViewBuilder, ViewIDMapper

logger = logging.getLogger(__name__)

ARCH_SYSTEM_PROMPT = """You are analyzing a codebase architecture from a symbol graph. Produce JSON with exactly these fields:
- "summary": 1-2 sentences describing the codebase
- "purpose": the primary purpose of this codebase
- "tags": array of 3-7 relevant tags
- "confidence": number between 0.0 and 1.0 indicating how confident you are
Respond ONLY with valid JSON."""

ARCH_USER_PROMPT = """Symbol graph statistics:
Total symbols: {total_symbols}
Languages: {languages}
Edge counts: {edge_stats}
Entry points: {entry_points}
Files: {file_count}"""


def _langs_from_counter(counter: Counter[str]) -> tuple[Language, list[Language]]:
    all_langs: list[Language] = []
    for lang_str in sorted(counter.keys()):
        try:
            all_langs.append(Language(lang_str))
        except ValueError:
            continue
    primary = all_langs[0] if all_langs else Language.PYTHON
    return primary, all_langs


class ArchViewBuilder(ViewBuilder):
    """Build ARCH view (1 entry) from symbol graph."""

    async def build(self, **kwargs) -> list[KBEntry]:
        nodes: list[SymbolNode] = kwargs["nodes"]
        edges: list[SymbolEdge] = kwargs["edges"]

        lang_counter: Counter[str] = Counter()
        for n in nodes:
            lang_counter[n.language.value] += 1

        edge_stats: dict[str, int] = {}
        for e in edges:
            key = e.kind.value
            edge_stats[key] = edge_stats.get(key, 0) + 1

        entry_points = self._find_entry_points(nodes)
        primary_lang, all_langs = _langs_from_counter(lang_counter)

        ai_data = AIData()
        if self._llm:
            user_prompt = ARCH_USER_PROMPT.format(
                total_symbols=len(nodes),
                languages=", ".join(l.value for l in all_langs),
                edge_stats=", ".join(f"{k}={v}" for k, v in sorted(edge_stats.items())),
                entry_points=", ".join(entry_points[:10]) or "none detected",
                file_count=len({n.path for n in nodes}),
            )
            try:
                result = await self._llm.complete(ARCH_SYSTEM_PROMPT, user_prompt)
                ai_data = AIData(
                    summary=result.get("summary"),
                    purpose=result.get("purpose"),
                    tags=result.get("tags", []),
                    confidence=result.get("confidence", 0.5),
                )
            except Exception as exc:
                logger.warning("ARCH LLM analysis failed: %s", exc)

        return [
            KBEntry(
                id="arch.root",
                layer=Layer.ARCH,
                static=StaticData(
                    kind=SymbolKind.PACKAGE,
                    language=primary_lang,
                    languages=all_langs,
                    path=".",
                    line_start=0,
                    line_end=0,
                    exports=entry_points,
                    source="graph",
                ),
                ai=ai_data,
            )
        ]

    @staticmethod
    def _find_entry_points(nodes: list[SymbolNode]) -> list[str]:
        names: list[str] = []
        for n in nodes:
            if n.name == "main":
                names.append(n.id)
            if Path(n.path).name == "__init__.py" and n.kind == SymbolKind.CLASS:
                names.append(n.id)
        return names
