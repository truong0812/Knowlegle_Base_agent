"""File watcher for auto-sync — detects source changes and triggers incremental rebuild."""
from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


class KBFileHandler(FileSystemEventHandler if HAS_WATCHDOG else object):
    """Watches source files and triggers incremental KB rebuild."""

    SOURCE_EXTENSIONS = {
        ".py", ".cs", ".cpp", ".hpp", ".h", ".cxx", ".cc",
        ".ts", ".js", ".tsx", ".jsx", ".java", ".go", ".rs",
        ".rb", ".php", ".swift", ".kt", ".dart",
    }

    def __init__(self, kb_dir: Path, repo_root: Path, debounce_seconds: float = 2.0) -> None:
        self._kb_dir = kb_dir
        self._repo_root = repo_root
        self._debounce_seconds = debounce_seconds
        self._changed_files: set[str] = set()
        self._last_rebuild = 0.0
        self._observer = None

    def start(self) -> None:
        if not HAS_WATCHDOG:
            logger.warning("watchdog not installed, auto-sync disabled")
            return
        self._observer = Observer()
        self._observer.schedule(self, str(self._repo_root), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        logger.info("File watcher started for %s", self._repo_root)

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)

    def on_any_event(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix not in self.SOURCE_EXTENSIONS:
            return

        # Skip files in .kb/ and common non-source dirs
        parts = path.parts
        skip_dirs = {".kb", "node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}
        if any(d in skip_dirs for d in parts):
            return

        rel = str(path.relative_to(self._repo_root))
        self._changed_files.add(rel)

        # Debounce: only rebuild after quiet period
        now = time.time()
        if now - self._last_rebuild >= self._debounce_seconds:
            self._rebuild()

    def _rebuild(self) -> None:
        if not self._changed_files:
            return

        changed = list(self._changed_files)
        self._changed_files.clear()
        self._last_rebuild = time.time()

        logger.info("Auto-sync: %d files changed, rebuilding...", len(changed))
        try:
            self._incremental_rebuild(changed)
        except Exception as exc:
            logger.error("Auto-sync rebuild failed: %s", exc)

    def _incremental_rebuild(self, changed_files: list[str]) -> None:
        """Incremental rebuild: re-parse changed files, update graph, re-index."""
        from kb_agent.parser.factory import get_parser
        from kb_agent.scanner.language import detect_language
        from kb_agent.graph.storage import GraphStorage

        graph_dir = self._kb_dir / "graph"
        if not graph_dir.exists():
            logger.warning("No graph found, skipping incremental rebuild")
            return

        storage = GraphStorage(graph_dir)
        nodes, edges = storage.load()

        # Build file-to-nodes index
        file_nodes: dict[str, list] = {}
        for node in nodes:
            file_nodes.setdefault(node.path, []).append(node)

        # Remove old nodes for changed files
        changed_node_ids: set[str] = set()
        for fp in changed_files:
            for node in file_nodes.get(fp, []):
                changed_node_ids.add(node.id)

        new_nodes = [n for n in nodes if n.id not in changed_node_ids]
        new_edges = [e for e in edges if e.source not in changed_node_ids and e.target not in changed_node_ids]

        # Re-parse changed files
        for fp in changed_files:
            full_path = self._repo_root / fp
            if not full_path.exists():
                continue
            lang = detect_language(fp)
            if not lang:
                continue
            try:
                parser = get_parser(lang)
                source = full_path.read_bytes()
                result = parser.parse_file(source, fp)
                from kb_agent.graph.builder import GraphBuilder
                builder = GraphBuilder(repo_name=self._repo_root.name)
                builder.build({fp: result}, repo_root=self._repo_root)
                new_nodes.extend(builder.nodes)
                new_edges.extend(builder.edges)
            except Exception as exc:
                logger.warning("Failed to re-parse %s: %s", fp, exc)

        storage.save(new_nodes, new_edges)
        logger.info("Auto-sync complete: %d nodes, %d edges", len(new_nodes), len(new_edges))

        # Rebuild FAISS index
        try:
            from kb_agent.indexer.indexer import KBIndexer
            from kb_agent.validator.validator import KBValidator
            entries = KBValidator(self._kb_dir)._load_entries()
            if entries:
                indexer = KBIndexer()
                indexer.build_index(entries, self._kb_dir / "index")
        except (ImportError, Exception) as exc:
            logger.debug("Index rebuild skipped: %s", exc)
