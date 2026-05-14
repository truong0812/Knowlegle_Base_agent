from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from kb_agent.models.entry import KBEntry
from kb_agent.models.manifest import KBStats, Manifest
from kb_agent.analyzer.arch_layer import ArchitectureAnalyzer
from kb_agent.analyzer.llm import LLMClient
from kb_agent.analyzer.mem_layer import MemberAnalyzer
from kb_agent.analyzer.mod_layer import ModuleAnalyzer
from kb_agent.parser.base import ParseResult
from kb_agent.parser.factory import get_parser
from kb_agent.scanner.scanner import FileScanner
from kb_agent.views.arch_view import ArchViewBuilder
from kb_agent.views.base import ViewIDMapper
from kb_agent.views.file_view import FileViewBuilder
from kb_agent.views.mem_view import MemViewBuilder
from kb_agent.views.mod_view import ModViewBuilder

logger = logging.getLogger(__name__)


class AnalysisPipeline:
    """Orchestrates the full 3-layer analysis pipeline."""

    def __init__(
        self,
        repo_root: Path,
        out_dir: Path,
        llm_client: LLMClient | None = None,
        build_graph: bool = False,
        module_depth: int = 1,
    ) -> None:
        self._repo_root = repo_root.resolve()
        self._out_dir = out_dir.resolve()
        self._llm = llm_client
        self._scanner = FileScanner(repo_root)
        self._build_graph = build_graph
        self._module_depth = module_depth

    async def run(self) -> Manifest:
        """Run full pipeline: scan → parse → graph (opt) → views/layers → write."""
        # 1. Scan
        file_entries = self._scanner.scan()
        if not file_entries:
            return Manifest(source_repo=str(self._repo_root))

        # 2. Parse all files
        parse_results = self._parse_all(file_entries)

        # 2.5. Build symbol graph (opt-in)
        if self._build_graph:
            try:
                self._build_and_save_graph(parse_results)
                all_entries = await self._materialize_views(parse_results)
            except Exception as exc:
                logger.error("Graph-based analysis failed, falling back to layers: %s", exc)
                all_entries = await self._run_layers(file_entries, parse_results)
        else:
            all_entries = await self._run_layers(file_entries, parse_results)

        # Write to disk
        manifest = self._write_entries(all_entries)

        # Build vector index
        self._build_index(all_entries)
        return manifest

    async def _run_layers(
        self, file_entries, parse_results: dict[str, ParseResult],
    ) -> list[KBEntry]:
        """Run legacy layer-based analysis (when --with-graph is not set)."""
        arch_analyzer = ArchitectureAnalyzer(self._llm)
        arch_entries = await arch_analyzer.analyze(file_entries, parse_results)

        mod_analyzer = ModuleAnalyzer(self._llm)
        mod_entries = await mod_analyzer.analyze(arch_entries, parse_results)

        mem_analyzer = MemberAnalyzer(self._llm)
        mem_entries = await mem_analyzer.analyze(mod_entries, parse_results)

        return self._link_entries(arch_entries, mod_entries, mem_entries)

    async def _materialize_views(self, parse_results: dict[str, ParseResult]) -> list[KBEntry]:
        """Build views from symbol graph instead of legacy layers."""
        from kb_agent.graph.storage import GraphStorage

        storage = GraphStorage(self._out_dir / "graph")
        nodes, edges = storage.load()
        mapper = ViewIDMapper(nodes, edges)

        arch = await ArchViewBuilder(mapper, self._llm).build(nodes=nodes, edges=edges)
        mod = await ModViewBuilder(mapper, self._llm, depth=self._module_depth).build(
            nodes=nodes, edges=edges, arch_entries=arch,
        )
        file = await FileViewBuilder(mapper, self._llm).build(
            edges=edges, mod_entries=mod,
        )
        mem = await MemViewBuilder(mapper, self._llm).build(
            nodes=nodes, edges=edges, mod_entries=mod, file_entries=file,
        )

        return self._link_entries(arch, mod, file, mem)

    def _build_and_save_graph(self, parse_results: dict[str, ParseResult]) -> None:
        """Build symbol graph from parse results and save to disk."""
        from kb_agent.graph.builder import GraphBuilder
        from kb_agent.graph.storage import GraphStorage

        builder = GraphBuilder(repo_name=self._repo_root.name)
        builder.build(parse_results, repo_root=self._repo_root)

        storage = GraphStorage(self._out_dir / "graph")
        storage.save(builder.nodes, builder.edges)

        logger.info(
            "Graph built: %d nodes, %d edges",
            len(builder.nodes), len(builder.edges),
        )

    def _parse_all(self, file_entries) -> dict[str, ParseResult]:
        """Parse every file. Returns dict keyed by rel_path."""
        results: dict[str, ParseResult] = {}
        for fe in file_entries:
            file_path = self._repo_root / fe.path
            try:
                source = file_path.read_bytes()
            except OSError:
                continue
            parser = get_parser(fe.language)
            result = parser.parse_file(source, fe.path)
            results[fe.path] = result
        return results

    def _link_entries(
        self,
        arch: list[KBEntry],
        mod: list[KBEntry],
        mem_or_file: list[KBEntry],
        mem: list[KBEntry] | None = None,
    ) -> list[KBEntry]:
        """Set children fields on parent entries."""
        entry_map: dict[str, KBEntry] = {}
        if mem is not None:
            all_entries = arch + mod + mem_or_file + mem
        else:
            all_entries = arch + mod + mem_or_file
        for entry in all_entries:
            entry_map[entry.id] = entry

        for entry in all_entries:
            if entry.parent and entry.parent in entry_map:
                parent = entry_map[entry.parent]
                if entry.id not in parent.children:
                    parent.children.append(entry.id)

        return all_entries

    def _write_entries(self, entries: list[KBEntry]) -> Manifest:
        """Write each entry as JSON to .kb/entries/. Write manifest.json."""
        entries_dir = self._out_dir / "entries"
        entries_dir.mkdir(parents=True, exist_ok=True)

        for entry in entries:
            # Flatten ID to valid filename
            filename = entry.id.replace(".", "_") + ".json"
            file_path = entries_dir / filename
            file_path.write_text(
                entry.model_dump_json(indent=2), encoding="utf-8"
            )

        # Build manifest
        by_layer: dict[str, int] = {"arch": 0, "mod": 0, "file": 0, "mem": 0}
        for entry in entries:
            by_layer[entry.layer.value] = by_layer.get(entry.layer.value, 0) + 1

        confidences = [e.ai.confidence for e in entries if e.ai.confidence > 0]

        manifest = Manifest(
            source_repo=str(self._repo_root),
            languages=list({e.static.language.value for e in entries}),
            stats=KBStats(
                total_entries=len(entries),
                by_layer=by_layer,
                coverage=1.0 if entries else 0.0,
                avg_confidence=sum(confidences) / len(confidences) if confidences else 0.0,
            ),
            created_at=datetime.now().isoformat(),
        )

        manifest_path = self._out_dir / "manifest.json"
        manifest_path.write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )

        return manifest

    def _build_index(self, entries: list[KBEntry]) -> None:
        """Build FAISS vector index from entries. Skips if dependencies missing."""
        import logging
        logger = logging.getLogger(__name__)

        try:
            from kb_agent.indexer.indexer import KBIndexer
            indexer = KBIndexer()
            indexer.build_index(entries, self._out_dir / "index")
        except ImportError:
            logger.info("Skipping index build — sentence-transformers/faiss not installed")
