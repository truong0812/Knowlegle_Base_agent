from __future__ import annotations

from pathlib import Path

from kb_agent.models.entry import AIData, KBEntry, Language, Layer, StaticData, SymbolKind
from kb_agent.analyzer.llm import LLMClient
from kb_agent.parser.base import ParseResult

MOD_SYSTEM_PROMPT = """You are analyzing a code module. Produce JSON with exactly these fields:
- "summary": 1-2 sentences describing the module
- "purpose": the module's purpose in the larger codebase
- "tags": array of relevant tags
Respond ONLY with valid JSON."""

MOD_USER_PROMPT = """Architecture context: {arch_summary}
Module: {module_path}
Symbols in this module:
{symbol_list}
Source files: {file_count}"""


class ModuleAnalyzer:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client

    async def analyze(
        self,
        arch_entries: list[KBEntry],
        parse_results: dict[str, ParseResult],
    ) -> list[KBEntry]:
        """Group files by top-level directory, produce module entries."""
        if not parse_results:
            return []

        arch_summary = arch_entries[0].ai.summary if arch_entries else ""

        # Group by top-level directory
        modules: dict[str, list[str]] = {}
        for rel_path in parse_results:
            parts = Path(rel_path).parts
            module_key = parts[0] if len(parts) > 1 else "."
            modules.setdefault(module_key, []).append(rel_path)

        entries: list[KBEntry] = []
        for module_key, file_paths in modules.items():
            # Collect all symbols from this module
            all_symbols: list[str] = []
            lang: Language | None = None
            for fp in file_paths:
                pr = parse_results[fp]
                lang = pr.language
                for sym in pr.symbols:
                    all_symbols.append(f"  {sym.kind.value} {sym.name}")

            ai_data = AIData()
            if self._llm:
                user_prompt = MOD_USER_PROMPT.format(
                    arch_summary=arch_summary,
                    module_path=module_key,
                    symbol_list="\n".join(all_symbols[:50]),
                    file_count=len(file_paths),
                )
                try:
                    result = await self._llm.complete(MOD_SYSTEM_PROMPT, user_prompt)
                    ai_data = AIData(
                        summary=result.get("summary"),
                        purpose=result.get("purpose"),
                        tags=result.get("tags", []),
                        confidence=0.85,
                    )
                except Exception:
                    pass

            entries.append(
                KBEntry(
                    id=f"mod.{module_key}",
                    layer=Layer.MOD,
                    parent="arch.root",
                    static=StaticData(
                        kind=SymbolKind.MODULE,
                        language=lang or Language.PYTHON,
                        path=module_key,
                        line_start=0,
                        line_end=0,
                        files=file_paths,
                        exports=[s.name for s in self._collect_symbols(file_paths, parse_results)],
                    ),
                    ai=ai_data,
                )
            )

        return entries

    def _collect_symbols(
        self, file_paths: list[str], parse_results: dict[str, ParseResult]
    ) -> list:
        symbols = []
        for fp in file_paths:
            symbols.extend(parse_results[fp].symbols)
        return symbols
