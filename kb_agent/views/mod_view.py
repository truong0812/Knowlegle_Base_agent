from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from kb_agent.analyzer.llm import LLMClient
from kb_agent.models.entry import AIData, KBEntry, Language, Layer, StaticData, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode

from .base import ViewBuilder, ViewIDMapper

logger = logging.getLogger(__name__)

MOD_SYSTEM_PROMPT = """You are analyzing a code module from a symbol graph. Produce JSON with exactly these fields:
- "summary": 1-2 sentences describing the module
- "purpose": the module's purpose in the larger codebase
- "tags": array of relevant tags
- "confidence": number between 0.0 and 1.0 indicating how confident you are
Respond ONLY with valid JSON."""

MOD_USER_PROMPT = """Architecture context: {arch_summary}
Module: {module_key}
Symbols in this module:
{symbol_list}
Source files: {file_count}
Import weights: business={business}, utility={utility}"""


class ModViewBuilder(ViewBuilder):
    """Build MOD view (N entries) from symbol graph."""

    def __init__(self, mapper: ViewIDMapper, llm: LLMClient | None = None, depth: int = 1) -> None:
        super().__init__(mapper, llm)
        self._depth = depth

    async def build(self, **kwargs) -> list[KBEntry]:
        nodes: list[SymbolNode] = kwargs["nodes"]
        edges: list[SymbolEdge] = kwargs["edges"]
        arch_entries: list[KBEntry] = kwargs.get("arch_entries", [])
        arch_summary = arch_entries[0].ai.summary if arch_entries else ""

        groups = self._mapper.group_nodes_by_depth(self._depth)
        filtered_edges = [e for e in edges if not self._is_utility_edge(e)]

        entries: list[KBEntry] = []
        for module_key, node_ids in groups.items():
            module_nodes = [self._mapper.node_by_id[nid] for nid in node_ids if nid in self._mapper.node_by_id]

            lang_counter: Counter[Language] = Counter()
            symbol_lines: list[str] = []
            file_paths: list[str] = []
            business_imports = 0
            utility_imports = 0

            for n in module_nodes:
                lang_counter[n.language] += 1
                symbol_lines.append(f"  {n.kind.value} {n.name}")

            unique_paths = {n.path for n in module_nodes}
            file_paths = sorted(unique_paths)

            for e in filtered_edges:
                if e.source in node_ids and e.kind == EdgeKind.IMPORTS:
                    target_node = self._mapper.node_by_id.get(e.target)
                    if target_node:
                        if ViewIDMapper.is_utility_name(target_node.name):
                            utility_imports += 1
                        else:
                            business_imports += 1

            ai_data = AIData()
            if self._llm:
                user_prompt = MOD_USER_PROMPT.format(
                    arch_summary=arch_summary,
                    module_key=module_key,
                    symbol_list="\n".join(symbol_lines[:50]),
                    file_count=len(file_paths),
                    business=business_imports,
                    utility=utility_imports,
                )
                try:
                    result = await self._llm.complete(MOD_SYSTEM_PROMPT, user_prompt)
                    ai_data = AIData(
                        summary=result.get("summary"),
                        purpose=result.get("purpose"),
                        tags=result.get("tags", []),
                        confidence=result.get("confidence", 0.5),
                    )
                except Exception as exc:
                    logger.warning("Module LLM analysis failed for %s: %s", module_key, exc)

            lang = lang_counter.most_common(1)[0][0] if lang_counter else Language.PYTHON

            entries.append(
                KBEntry(
                    id=f"mod.{module_key}",
                    layer=Layer.MOD,
                    parent="arch.root",
                    static=StaticData(
                        kind=SymbolKind.MODULE,
                        language=lang,
                        path=module_key,
                        line_start=0,
                        line_end=0,
                        files=file_paths,
                        exports=[n.name for n in module_nodes if n.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION)],
                        source="graph",
                    ),
                    ai=ai_data,
                )
            )

        return entries

    def _is_utility_edge(self, edge: SymbolEdge) -> bool:
        target = self._mapper.node_by_id.get(edge.target)
        if target and ViewIDMapper.is_utility_name(target.name):
            return True
        source = self._mapper.node_by_id.get(edge.source)
        if source and ViewIDMapper.is_utility_name(source.name):
            return True
        return False
