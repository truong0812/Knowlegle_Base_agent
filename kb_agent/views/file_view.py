from __future__ import annotations

import logging
from pathlib import Path

from kb_agent.analyzer.llm import LLMClient
from kb_agent.models.entry import AIData, KBEntry, Layer, StaticData, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode

from .base import ViewBuilder, ViewIDMapper

logger = logging.getLogger(__name__)

FILE_SYSTEM_PROMPT = """You are analyzing a source file from a symbol graph. Produce JSON with exactly these fields:
- "summary": 1-2 sentences describing the file's role
- "purpose": what this file contributes to the codebase
- "tags": array of relevant tags
- "confidence": number between 0.0 and 1.0
Respond ONLY with valid JSON."""

FILE_USER_PROMPT = """Module context: {mod_summary}
File: {file_path}
Language: {language}
Symbols:
{symbol_tree}
Intra-file edges:
{intra_edges}
External dependencies:
{external_deps}"""


class FileViewBuilder(ViewBuilder):
    """Build FILE view (F entries, one per file) from symbol graph."""

    async def build(self, **kwargs) -> list[KBEntry]:
        edges: list[SymbolEdge] = kwargs["edges"]
        mod_entries: list[KBEntry] = kwargs.get("mod_entries", [])

        mod_for_file = self._build_mod_lookup(mod_entries)
        mod_summaries = {m.id: m.ai.summary or "" for m in mod_entries}

        # Pre-classify edges: node_id -> file_path lookup
        node_to_file = self._build_node_to_file_map()
        edge_by_file = self._classify_edges_by_file(edges, node_to_file)

        entries: list[KBEntry] = []
        for file_path, node_ids in self._mapper.nodes_by_path.items():
            file_nodes = [self._mapper.node_by_id[nid] for nid in node_ids if nid in self._mapper.node_by_id]

            if not file_nodes:
                continue

            intra, external = edge_by_file.get(file_path, ([], []))

            lang = file_nodes[0].language
            line_start = min(n.line_start for n in file_nodes)
            line_end = max(n.line_end for n in file_nodes)

            symbol_tree = self._build_symbol_tree(file_nodes)
            intra_desc = [f"  {e.kind.value}: {self._short_id(e.source)} -> {self._short_id(e.target)}" for e in intra[:20]]
            ext_targets = set()
            for e in external:
                t = self._mapper.node_by_id.get(e.target)
                if t:
                    ext_targets.add(f"{t.name} ({t.path})")

            mod_id = mod_for_file.get(file_path)
            mod_summary = mod_summaries.get(mod_id or "", "")

            ai_data = AIData()
            if self._llm:
                user_prompt = FILE_USER_PROMPT.format(
                    mod_summary=mod_summary,
                    file_path=file_path,
                    language=lang.value,
                    symbol_tree=symbol_tree,
                    intra_edges="\n".join(intra_desc) or "  none",
                    external_deps="\n".join(f"  {t}" for t in sorted(ext_targets)[:20]) or "  none",
                )
                try:
                    result = await self._llm.complete(FILE_SYSTEM_PROMPT, user_prompt)
                    ai_data = AIData(
                        summary=result.get("summary"),
                        purpose=result.get("purpose"),
                        tags=result.get("tags", []),
                        confidence=result.get("confidence", 0.5),
                    )
                except Exception as exc:
                    logger.warning("FILE LLM analysis failed for %s: %s", file_path, exc)

            sanitized = ViewIDMapper.sanitize_path(file_path)
            exports = [n.name for n in file_nodes if n.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION)]
            imports_list = sorted(ext_targets)[:50]

            entries.append(
                KBEntry(
                    id=f"file.{sanitized}",
                    layer=Layer.FILE,
                    parent=mod_id,
                    static=StaticData(
                        kind=SymbolKind.MODULE,
                        language=lang,
                        path=file_path,
                        line_start=line_start,
                        line_end=line_end,
                        imports=imports_list,
                        exports=exports,
                        files=[file_path],
                        source="graph",
                    ),
                    ai=ai_data,
                )
            )

        return entries

    def _build_node_to_file_map(self) -> dict[str, str]:
        """Pre-build node_id -> file_path for O(1) edge classification."""
        mapping: dict[str, str] = {}
        for file_path, node_ids in self._mapper.nodes_by_path.items():
            for nid in node_ids:
                mapping[nid] = file_path
        return mapping

    def _classify_edges_by_file(
        self, edges: list[SymbolEdge], node_to_file: dict[str, str],
    ) -> dict[str, tuple[list[SymbolEdge], list[SymbolEdge]]]:
        """Classify all edges into intra/external per file in a single pass."""
        result: dict[str, tuple[list[SymbolEdge], list[SymbolEdge]]] = {}
        for e in edges:
            src_file = node_to_file.get(e.source)
            tgt_file = node_to_file.get(e.target)
            if src_file is None and tgt_file is None:
                continue
            if src_file and src_file == tgt_file:
                if src_file not in result:
                    result[src_file] = ([], [])
                result[src_file][0].append(e)
            else:
                if src_file:
                    if src_file not in result:
                        result[src_file] = ([], [])
                    result[src_file][1].append(e)
                if tgt_file and tgt_file != src_file:
                    if tgt_file not in result:
                        result[tgt_file] = ([], [])
                    result[tgt_file][1].append(e)
        return result

    def _build_mod_lookup(self, mod_entries: list[KBEntry]) -> dict[str, str | None]:
        lookup: dict[str, str | None] = {}
        for mod in mod_entries:
            for fp in (mod.static.files or []):
                lookup[fp] = mod.id
        return lookup

    def _build_symbol_tree(self, nodes: list[SymbolNode]) -> str:
        lines: list[str] = []
        top_level = [n for n in nodes if n.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION, SymbolKind.STRUCT, SymbolKind.INTERFACE, SymbolKind.ENUM)]
        for n in top_level:
            lines.append(f"  {n.kind.value} {n.name}")
            if n.signature:
                lines.append(f"    signature: {n.signature}")
        return "\n".join(lines) if lines else "  (no symbols)"

    def _short_id(self, node_id: str) -> str:
        node = self._mapper.node_by_id.get(node_id)
        if node:
            return node.name
        parts = node_id.split("::")
        return parts[-1] if parts else node_id
