from __future__ import annotations

from pathlib import Path

from kb_agent.models.entry import Language

EXTENSION_MAP: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".cs": Language.CSHARP,
    ".cpp": Language.CPP,
    ".hpp": Language.CPP,
    ".h": Language.CPP,
    ".cxx": Language.CPP,
    ".cc": Language.CPP,
}


def detect_language(file_path: Path) -> Language | None:
    """Detect language from file extension. Returns None for unsupported files."""
    return EXTENSION_MAP.get(file_path.suffix.lower())
