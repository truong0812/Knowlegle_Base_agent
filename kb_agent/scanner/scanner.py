from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from kb_agent.models.entry import Language
from kb_agent.scanner.ignore import DEFAULT_IGNORE_DIRS, KbignoreMatcher
from kb_agent.scanner.language import detect_language


class FileEntry(BaseModel):
    """Lightweight model for scanner output."""

    path: str
    language: Language
    size_bytes: int


class FileScanner:
    """Walk repo, filter ignored paths, detect language per file."""

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root.resolve()
        self._ignore = KbignoreMatcher(self._root)

    def scan(self) -> list[FileEntry]:
        results: list[FileEntry] = []
        for root, dirs, files in self._walk():
            for fname in files:
                fpath = Path(root) / fname
                rel = fpath.relative_to(self._root)
                rel_str = str(rel).replace("\\", "/")

                if self._ignore.should_ignore(rel_str):
                    continue

                lang = detect_language(fpath)
                if lang is None:
                    continue

                try:
                    size = fpath.stat().st_size
                except OSError:
                    size = 0

                results.append(
                    FileEntry(path=rel_str, language=lang, size_bytes=size)
                )
        return results

    def _walk(self):
        """Walk repo, skipping ignored directories."""
        ignore_dirs = DEFAULT_IGNORE_DIRS
        for root, dirs, files in os.walk(self._root):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            yield Path(root), dirs, files

    def build_directory_tree(self) -> dict:
        """Return nested dict representing folder structure."""
        tree: dict = {}
        entries = self.scan()
        for entry in entries:
            parts = Path(entry.path).parent.parts
            node = tree
            for part in parts:
                if part not in node:
                    node[part] = {}
                node = node[part]
        return tree
