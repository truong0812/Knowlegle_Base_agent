"""Auto-initialize KB when entering a project."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_kb_initialized(kb_dir: Path, repo_root: Path | None = None) -> bool:
    """Check if .kb/ exists, and auto-initialize if not.

    Returns True if KB is available (existing or just created).
    Messages go to stderr to avoid corrupting MCP stdio protocol.
    """
    kb_dir = kb_dir.resolve()
    if kb_dir.exists() and (kb_dir / "manifest.json").exists():
        return True

    if repo_root is None:
        repo_root = kb_dir.parent
    repo_root = repo_root.resolve()

    # Check if there are source files
    source_exts = {".py", ".cs", ".cpp", ".hpp", ".h", ".cxx", ".cc"}
    has_source = any(
        any(Path(root) / f for f in files if Path(f).suffix in source_exts)
        for root, _, files in _walk_safe(repo_root, max_depth=3)
    )
    if not has_source:
        return False

    print(f"[kb-agent] Auto-initializing knowledge base for {repo_root}...", file=sys.stderr)

    try:
        from kb_agent.analyzer.pipeline import AnalysisPipeline
        import asyncio

        pipeline = AnalysisPipeline(
            repo_root=repo_root,
            out_dir=kb_dir,
            llm_client=None,  # Skip AI for auto-init (fast)
            build_graph=True,
        )
        manifest = asyncio.run(pipeline.run())
        print(
            f"[kb-agent] Initialized: {manifest.stats.total_entries} entries, "
            f"graph with {manifest.stats.by_layer}",
            file=sys.stderr,
        )
        return True
    except Exception as exc:
        print(f"[kb-agent] Auto-init failed: {exc}", file=sys.stderr)
        return False


def _walk_safe(root: Path, max_depth: int = 3):
    """Walk directory tree with depth limit, skipping common non-source dirs."""
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".kb"}

    def _walk(current: Path, depth: int):
        if depth > max_depth:
            return
        try:
            entries = list(current.iterdir())
        except PermissionError:
            return

        dirs = []
        files = []
        for entry in entries:
            if entry.is_dir():
                if entry.name not in skip_dirs:
                    dirs.append(entry)
            else:
                files.append(entry.name)

        yield str(current), [d.name for d in dirs], files
        for d in dirs:
            yield from _walk(d, depth + 1)

    yield from _walk(root, 0)
