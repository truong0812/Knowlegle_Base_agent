from __future__ import annotations

import fnmatch
from pathlib import Path


DEFAULT_IGNORE_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "target",
    "bin",
    "obj",
    "venv",
    ".venv",
    "__pycache__",
    ".idea",
    ".vscode",
}


class KbignoreMatcher:
    """Loads .kbignore patterns and tests file paths against them."""

    def __init__(self, repo_root: Path) -> None:
        self._patterns: list[str] = []
        kbignore = repo_root / ".kbignore"
        if kbignore.exists():
            for line in kbignore.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    self._patterns.append(stripped)

    def should_ignore(self, rel_path: str) -> bool:
        """Check if a relative path matches any .kbignore pattern."""
        for pattern in self._patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            # Handle directory patterns like "vendor/" — match any file under that dir
            if pattern.endswith("/"):
                dir_prefix = pattern[:-1]
                if rel_path.startswith(dir_prefix + "/") or rel_path == dir_prefix:
                    return True
            # Also match if any parent segment matches the pattern
            parts = Path(rel_path).parts
            for part in parts[:-1]:
                if fnmatch.fnmatch(part, pattern.rstrip("/")):
                    return True
        return False
