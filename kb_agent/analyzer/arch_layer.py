from __future__ import annotations

import logging
from pathlib import Path

from kb_agent.models.entry import AIData, KBEntry, Layer, Language, StaticData, SymbolKind
from kb_agent.analyzer.llm import LLMClient
from kb_agent.parser.base import ParseResult
from kb_agent.scanner.scanner import FileEntry, build_tree_from_entries

logger = logging.getLogger(__name__)

ARCH_SYSTEM_PROMPT = """You are analyzing a codebase architecture. Produce JSON with exactly these fields:
- "summary": 1-2 sentences describing the codebase
- "purpose": the primary purpose of this codebase
- "tags": array of 3-7 relevant tags
- "confidence": number between 0.0 and 1.0 indicating how confident you are
Respond ONLY with valid JSON."""

ARCH_USER_PROMPT = """Directory structure:
{folder_tree}

Languages detected: {languages}
Total files: {total_files}"""


class ArchitectureAnalyzer:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client

    async def analyze(
        self,
        file_entries: list[FileEntry],
        parse_results: dict[str, ParseResult],
    ) -> list[KBEntry]:
        """Produce architecture-level entries."""
        if not file_entries:
            return []

        # Build folder tree
        langs: set[str] = set()
        for entry in file_entries:
            langs.add(entry.language.value)

        tree = build_tree_from_entries(file_entries)
        folder_tree = json_tree(tree)
        ai_data = AIData()

        if self._llm:
            user_prompt = ARCH_USER_PROMPT.format(
                folder_tree=folder_tree,
                languages=", ".join(sorted(langs)),
                total_files=len(file_entries),
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
                logger.warning("Architecture LLM analysis failed: %s", exc)

        primary_lang, all_langs = langs_populate(langs)

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
                ),
                ai=ai_data,
            )
        ]


def langs_populate(langs: set[str]) -> tuple[Language, list[Language]]:
    """Return (primary_language, all_languages) for detected languages."""
    all_langs = []
    for lang_str in sorted(langs):
        try:
            all_langs.append(Language(lang_str))
        except ValueError:
            continue
    primary = all_langs[0] if all_langs else Language.PYTHON
    return primary, all_langs


def json_tree(tree: dict, indent: int = 0) -> str:
    lines: list[str] = []
    for key, val in tree.items():
        lines.append("  " * indent + key + "/")
        if isinstance(val, dict):
            lines.append(json_tree(val, indent + 1))
    return "\n".join(lines)
