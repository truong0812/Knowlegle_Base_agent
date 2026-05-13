from __future__ import annotations

from pathlib import Path

from kb_agent.models.entry import (
    AIData,
    KBEntry,
    Language,
    Layer,
    StaticData,
    SymbolKind,
)
from kb_agent.analyzer.llm import LLMClient
from kb_agent.parser.base import ParseResult

MEM_SYSTEM_PROMPT = """You are analyzing a single code symbol. Produce JSON with exactly these fields:
- "summary": 1 sentence describing what this symbol does
- "behavior": array of steps describing the logic
- "tags": array of relevant tags
- "confidence": number between 0.0 and 1.0
Respond ONLY with valid JSON."""

MEM_USER_PROMPT = """Module context: {mod_summary}
Symbol: {name} ({kind})
Signature: {signature}
Source:
{source}"""


class MemberAnalyzer:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client

    async def analyze(
        self,
        mod_entries: list[KBEntry],
        parse_results: dict[str, ParseResult],
    ) -> list[KBEntry]:
        """Produce member-level entries from parsed symbols."""
        # Build a lookup: file_path -> module_id
        file_to_module: dict[str, str] = {}
        mod_summaries: dict[str, str] = {}
        for mod in mod_entries:
            mod_summaries[mod.id] = mod.ai.summary or ""
            files = mod.static.files or []
            for fp in files:
                file_to_module[fp] = mod.id

        entries: list[KBEntry] = []
        for rel_path, pr in parse_results.items():
            module_id = file_to_module.get(rel_path)
            mod_summary = mod_summaries.get(module_id or "", "")

            all_symbols = self._flatten_symbols(pr.symbols)
            for sym in all_symbols:
                entry_id = self._build_entry_id(sym, rel_path, module_id)

                ai_data = AIData()
                if self._llm and sym.signature:
                    user_prompt = MEM_USER_PROMPT.format(
                        mod_summary=mod_summary,
                        name=sym.name,
                        kind=sym.kind.value,
                        signature=sym.signature,
                        source=sym.signature,
                    )
                    try:
                        result = await self._llm.complete(MEM_SYSTEM_PROMPT, user_prompt)
                        ai_data = AIData(
                            summary=result.get("summary"),
                            behavior=result.get("behavior", []),
                            tags=result.get("tags", []),
                            confidence=result.get("confidence", 0.5),
                        )
                    except Exception:
                        pass

                entries.append(
                    KBEntry(
                        id=entry_id,
                        layer=Layer.MEM,
                        parent=module_id,
                        static=StaticData(
                            kind=sym.kind,
                            language=pr.language,
                            path=rel_path,
                            line_start=sym.line_start,
                            line_end=sym.line_end,
                            signature=sym.signature,
                            modifiers=sym.modifiers,
                            parameters=sym.parameters,
                            return_type=sym.return_type,
                            docstring=sym.docstring,
                        ),
                        ai=ai_data,
                    )
                )

        return entries

    def _flatten_symbols(self, symbols: list) -> list:
        """Flatten nested symbols (class children) into a flat list."""
        flat: list = []
        for sym in symbols:
            flat.append(sym)
            for child in sym.children:
                flat.append(child)
        return flat

    def _build_entry_id(
        self, sym, rel_path: str, module_id: str | None
    ) -> str:
        """Construct dotted-path entry ID."""
        parts = ["mem"]
        if module_id:
            # mod.src -> src
            parts.append(module_id.replace("mod.", "", 1))

        path_stem = Path(rel_path).stem
        parts.append(path_stem)
        parts.append(sym.name)
        return ".".join(parts)
