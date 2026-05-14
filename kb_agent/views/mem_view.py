from __future__ import annotations

import logging
from pathlib import Path

from kb_agent.analyzer.llm import LLMClient
from kb_agent.models.entry import AIData, KBEntry, Layer, StaticData, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode

from .base import ViewBuilder, ViewIDMapper

logger = logging.getLogger(__name__)

MEM_SYSTEM_PROMPT = """You are analyzing a single code symbol with graph context. Produce JSON with exactly these fields:
- "summary": 1 sentence describing what this symbol does
- "behavior": array of steps describing the logic
- "tags": array of relevant tags
- "confidence": number between 0.0 and 1.0
Respond ONLY with valid JSON."""

MEM_USER_PROMPT = """Module context: {mod_summary}
Symbol: {name} ({kind})
Signature: {signature}
Calls: {calls}
Uses types: {types}
Source:
{source}"""


class MemViewBuilder(ViewBuilder):
    """Build MEM view (M entries, one per symbol node) from symbol graph."""

    async def build(self, **kwargs) -> list[KBEntry]:
        nodes: list[SymbolNode] = kwargs["nodes"]
        edges: list[SymbolEdge] = kwargs["edges"]
        mod_entries: list[KBEntry] = kwargs.get("mod_entries", [])
        file_entries: list[KBEntry] = kwargs.get("file_entries", [])

        mod_for_file = self._build_mod_lookup(mod_entries)
        mod_summaries = {m.id: m.ai.summary or "" for m in mod_entries}

        entries: list[KBEntry] = []
        for node in nodes:
            outgoing = self._mapper.edges_by_source.get(node.id, [])
            calls = [self._short_id(e.target) for e in outgoing if e.kind == EdgeKind.CALLS]
            types_used = [self._short_id(e.target) for e in outgoing if e.kind == EdgeKind.USES_TYPE]

            module_key = self._mapper.find_module_for_file(node.path, self._depth(mod_entries))
            mod_id = None
            for m in mod_entries:
                if node.path in (m.static.files or []):
                    mod_id = m.id
                    break

            mod_summary = mod_summaries.get(mod_id or "", "")
            parent_name = self._find_parent_name(node, edges)

            entry_id = self._build_entry_id(node, module_key, parent_name)

            ai_data = AIData()
            if self._llm and node.signature:
                user_prompt = MEM_USER_PROMPT.format(
                    mod_summary=mod_summary,
                    name=node.name,
                    kind=node.kind.value,
                    signature=node.signature,
                    calls=", ".join(calls[:10]) or "none",
                    types=", ".join(types_used[:10]) or "none",
                    source=node.signature,
                )
                try:
                    result = await self._llm.complete(MEM_SYSTEM_PROMPT, user_prompt)
                    ai_data = AIData(
                        summary=result.get("summary"),
                        behavior=result.get("behavior", []),
                        tags=result.get("tags", []),
                        confidence=result.get("confidence", 0.5),
                    )
                except Exception as exc:
                    logger.warning("MEM LLM analysis failed for %s: %s", node.name, exc)

            imports_out = [self._short_id(e.target) for e in outgoing if e.kind == EdgeKind.IMPORTS]

            entries.append(
                KBEntry(
                    id=entry_id,
                    layer=Layer.MEM,
                    parent=mod_id,
                    static=StaticData(
                        kind=node.kind,
                        language=node.language,
                        path=node.path,
                        line_start=node.line_start,
                        line_end=node.line_end,
                        signature=node.signature,
                        modifiers=node.modifiers,
                        parameters=node.parameters,
                        return_type=node.return_type,
                        docstring=node.docstring,
                        imports=imports_out,
                        source="graph",
                    ),
                    ai=ai_data,
                )
            )

        return entries

    def _build_entry_id(self, node: SymbolNode, module_key: str, parent_name: str | None) -> str:
        parts = ["mem", module_key]
        file_stem = Path(node.path).stem
        parts.append(file_stem)
        if parent_name and node.kind in (SymbolKind.FUNCTION, SymbolKind.METHOD):
            parts.append(parent_name.lower())
        parts.append(node.name)
        base_id = ".".join(parts)
        return f"{base_id}_L{node.line_start}"

    def _find_parent_name(self, node: SymbolNode, edges: list[SymbolEdge]) -> str | None:
        for e in edges:
            if e.target == node.id and e.kind == EdgeKind.CONTAINS:
                parent = self._mapper.node_by_id.get(e.source)
                if parent:
                    return parent.name
        return None

    def _build_mod_lookup(self, mod_entries: list[KBEntry]) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for m in mod_entries:
            for fp in (m.static.files or []):
                lookup[fp] = m.id
        return lookup

    @staticmethod
    def _depth(mod_entries: list[KBEntry]) -> int:
        if not mod_entries:
            return 1
        sample = mod_entries[0]
        parts = Path(sample.static.path).parts
        return len(parts) if parts else 1

    def _short_id(self, node_id: str) -> str:
        node = self._mapper.node_by_id.get(node_id)
        if node:
            return node.name
        parts = node_id.split("::")
        return parts[-1] if parts else node_id
