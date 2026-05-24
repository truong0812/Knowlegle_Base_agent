from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from kb_agent.analyzer.arch_layer import ARCH_SYSTEM_PROMPT, ARCH_USER_PROMPT
from kb_agent.analyzer.llm import LLMClient
from kb_agent.analyzer.mem_layer import MEM_SYSTEM_PROMPT, MEM_USER_PROMPT
from kb_agent.analyzer.mod_layer import MOD_SYSTEM_PROMPT, MOD_USER_PROMPT
from kb_agent.models.entry import AIData, KBEntry, Layer

logger = logging.getLogger(__name__)

LAYER_PROMPTS = {
    Layer.ARCH: (ARCH_SYSTEM_PROMPT, "arch"),
    Layer.MOD: (MOD_SYSTEM_PROMPT, "mod"),
    Layer.MEM: (MEM_SYSTEM_PROMPT, "mem"),
}


class Enricher:
    """Incrementally enrich KB entries with LLM data."""

    def __init__(self, kb_dir: Path, llm_client: LLMClient) -> None:
        self._kb_dir = kb_dir
        self._llm = llm_client
        self._entries_dir = kb_dir / "entries"
        llm_client.set_failure_log(kb_dir / "telemetry" / "llm_failures.jsonl")

    async def enrich(
        self,
        retry_failed: bool = False,
        layers: list[Layer] | None = None,
        progress_callback=None,
    ) -> dict:
        """Enrich entries missing AI data. Returns stats dict."""
        entries = self._load_entries()
        if not entries:
            return {"total": 0, "enriched": 0, "skipped": 0, "failed": 0}

        target_layers = set(layers) if layers else {Layer.ARCH, Layer.MOD, Layer.MEM}
        failed_ids = set()

        if retry_failed:
            failed_ids = self._load_failed_ids()

        to_enrich = []
        for entry in entries:
            if entry.layer not in target_layers:
                continue
            needs_enrichment = (
                entry.ai.summary is None or entry.id in failed_ids
            )
            if needs_enrichment:
                to_enrich.append(entry)

        if not to_enrich:
            return {"total": len(entries), "enriched": 0, "skipped": len(entries), "failed": 0}

        prompts = []
        entry_ids = []
        for entry in to_enrich:
            prompt_info = LAYER_PROMPTS.get(entry.layer)
            if not prompt_info:
                continue
            sys_prompt, _ = prompt_info
            user_prompt = self._build_user_prompt(entry)
            prompts.append((sys_prompt, user_prompt))
            entry_ids.append(entry.id)

        results = await self._llm.batch_complete(
            prompts, entry_ids=entry_ids, progress_callback=progress_callback,
        )

        enriched = 0
        failed = 0
        for entry, result in zip(to_enrich, results):
            if result:
                entry.ai = AIData(
                    summary=result.get("summary"),
                    purpose=result.get("purpose"),
                    behavior=result.get("behavior", []),
                    tags=result.get("tags", []),
                    confidence=result.get("confidence", 0.5),
                )
                self._save_entry(entry)
                enriched += 1
            else:
                failed += 1

        # Rebuild FAISS index
        self._rebuild_index(entries)

        return {
            "total": len(entries),
            "enriched": enriched,
            "skipped": len(entries) - len(to_enrich),
            "failed": failed,
        }

    def _build_user_prompt(self, entry: KBEntry) -> str:
        if entry.layer == Layer.ARCH:
            return ARCH_USER_PROMPT.format(
                folder_tree=entry.static.path,
                languages=", ".join(entry.static.languages or []),
                total_files=0,
            )
        if entry.layer == Layer.MOD:
            symbols = entry.static.exports or []
            return MOD_USER_PROMPT.format(
                arch_summary="",
                module_path=entry.static.path,
                symbol_list="\n".join(f"  {s}" for s in symbols[:50]),
                file_count=len(entry.static.files or []),
            )
        if entry.layer == Layer.MEM:
            return MEM_USER_PROMPT.format(
                mod_summary="",
                name=entry.static.signature or entry.id,
                kind=entry.static.kind.value,
                signature=entry.static.signature or "",
                source=entry.static.signature or "",
            )
        return f"Describe this code element: {entry.id}"

    def _load_entries(self) -> list[KBEntry]:
        entries = []
        if not self._entries_dir.exists():
            return entries
        for f in sorted(self._entries_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                entries.append(KBEntry(**data))
            except Exception:
                continue
        return entries

    def _save_entry(self, entry: KBEntry) -> None:
        from kb_agent.query.engine import entry_filename
        filename = entry_filename(entry.id)
        path = self._entries_dir / filename
        path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")

    def _load_failed_ids(self) -> set[str]:
        failure_file = self._kb_dir / "telemetry" / "llm_failures.jsonl"
        if not failure_file.exists():
            return set()
        ids = set()
        for line in failure_file.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                if record.get("entry_id"):
                    ids.add(record["entry_id"])
            except json.JSONDecodeError:
                continue
        return ids

    def _rebuild_index(self, entries: list[KBEntry]) -> None:
        try:
            from kb_agent.indexer.indexer import KBIndexer
            graph_dir = self._kb_dir / "graph"
            graph_dir = graph_dir if graph_dir.exists() else None
            indexer = KBIndexer()
            indexer.build_index(entries, self._kb_dir / "index", graph_dir=graph_dir)
        except (ImportError, Exception) as exc:
            logger.warning("Index rebuild skipped: %s", exc)
