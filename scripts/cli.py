#!/usr/bin/env python3
# language: python
"""
Enhanced CLI scaffold for KB-Agent (scanner + language-detector).
Run: python scripts/cli.py scan --repo /path/to/repo --out .kb/artifacts
Adds:
- repo-level manifest detection (e.g., .csproj, package.json, pyproject.toml)
- optional .kbignore handling
- better fallback assignment for C# and Python when manifests present
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple
import fnmatch
import typer

app = typer.Typer(help="KB-Agent CLI (MVP scaffold)")

DEFAULT_IGNORE_DIRS = {"node_modules", ".git", "dist", "build", "venv", ".venv"}
EXT_LANG_MAP: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".swift": "swift",
    ".csproj": "csharp",
    ".sln": "csharp",
}

MANIFEST_PATTERNS = [
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "pom.xml",
    "build.gradle",
    "go.mod",
    "*.csproj",
    "*.sln",
]

def read_kbignore(repo: Path) -> List[str]:
    kbignore = repo / ".kbignore"
    patterns: List[str] = []
    if kbignore.exists():
        try:
            with kbignore.open("r", encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if not s or s.startswith("#"):
                        continue
                    patterns.append(s)
        except Exception:
            pass
    return patterns

def matches_ignore(path: Path, repo: Path, ignore_dirs: Set[str], kbignore_patterns: List[str]) -> bool:
    # directory-based ignore
    for part in path.relative_to(repo).parents:
        if part.name in ignore_dirs:
            return True
    # file/directory pattern ignore from .kbignore
    rel = str(path.relative_to(repo)).replace("\\", "/")
    for pat in kbignore_patterns:
        if fnmatch.fnmatch(rel, pat):
            return True
    return False

def detect_repo_manifests(repo: Path) -> Set[str]:
    langs: Set[str] = set()
    for root, dirs, files in os.walk(repo):
        for pat in MANIFEST_PATTERNS:
            for fname in files:
                if fnmatch.fnmatch(fname, pat):
                    fpath = Path(root) / fname
                    if fname.endswith("package.json"):
                        langs.add("javascript")
                    if fname.endswith("requirements.txt") or fname.endswith("pyproject.toml") or fname == "setup.py":
                        langs.add("python")
                    if fname.endswith(".csproj") or fname.endswith(".sln"):
                        langs.add("csharp")
                    if fname.endswith("pom.xml") or pat == "pom.xml":
                        langs.add("java")
                    if fname == "go.mod":
                        langs.add("go")
    return langs

def detect_language(path: Path, repo_lang_hints: Set[str]) -> Tuple[str, float, List[dict]]:
    ext = path.suffix.lower()
    evidence: List[dict] = []
    if ext in EXT_LANG_MAP:
        evidence.append({"type": "extension", "value": ext})
        return EXT_LANG_MAP[ext], 0.99, evidence

    # try shebang for scripts
    try:
        with path.open("r", encoding="utf-8") as f:
            first = f.readline()
            if first.startswith("#!"):
                if "python" in first:
                    evidence.append({"type": "shebang", "value": first.strip()})
                    return "python", 0.9, evidence
    except Exception:
        pass

    # fallback to repo-level hints
    if repo_lang_hints:
        # prefer Python or C# if present (as requested)
        if "python" in repo_lang_hints:
            evidence.append({"type": "repo_manifest", "value": "python"})
            return "python", 0.60, evidence
        if "csharp" in repo_lang_hints:
            evidence.append({"type": "repo_manifest", "value": "csharp"})
            return "csharp", 0.60, evidence
        # otherwise pick one hint (low confidence)
        lang = next(iter(repo_lang_hints))
        evidence.append({"type": "repo_manifest", "value": lang})
        return lang, 0.5, evidence

    # unknown
    evidence.append({"type": "fallback", "value": "unknown"})
    return "unknown", 0.1, evidence

@app.command()
def scan(repo: Path = typer.Option(Path("."), help="Path to repository"),
         out: Path = typer.Option(Path(".kb/artifacts"), help="Output artifact dir"),
         include_hidden: bool = typer.Option(False, help="Include hidden files"),
         extra_ignore: List[str] = typer.Option(None, help="Additional directories or patterns to ignore")):
    """
    Scan repository files and produce .kb/artifacts/files.json with per-file language metadata.
    Enhanced:
    - reads .kbignore patterns if present
    - detects repo manifests to provide language hints (e.g., C# + Python)
    """
    repo = repo.resolve()
    out = out.resolve()
    ignore_dirs = set(DEFAULT_IGNORE_DIRS)
    if extra_ignore:
        for p in extra_ignore:
            ignore_dirs.add(p)

    kbignore_patterns = read_kbignore(repo)
    repo_lang_hints = detect_repo_manifests(repo)

    artifacts_files: List[dict] = []
    for root, dirs, files in os.walk(repo):
        # filter ignore dirs
        dirs[:] = [d for d in dirs if d not in ignore_dirs and (include_hidden or not d.startswith("."))]
        for fname in files:
            if not include_hidden and fname.startswith("."):
                continue
            fpath = Path(root) / fname
            rel = fpath.relative_to(repo)
            # skip artifacts dir itself
            try:
                if str(rel).startswith(str(out.relative_to(repo))):
                    continue
            except Exception:
                pass
            # skip matches from .kbignore or default ignore
            if matches_ignore(fpath, repo, ignore_dirs, kbignore_patterns):
                continue

            lang, conf, evidence = detect_language(fpath, repo_lang_hints)
            try:
                size = fpath.stat().st_size
            except Exception:
                size = 0
            artifacts_files.append({
                "path": str(rel).replace("\\", "/"),
                "abs_path": str(fpath),
                "size": size,
                "language": lang,
                "confidence": conf,
                "evidence": evidence
            })

    out.mkdir(parents=True, exist_ok=True)
    files_json = out / "files.json"
    with files_json.open("w", encoding="utf-8") as fh:
        json.dump(artifacts_files, fh, ensure_ascii=False, indent=2)

    typer.echo(f"Wrote {len(artifacts_files)} entries to {files_json}")
    if repo_lang_hints:
        typer.echo(f"Repo language hints detected: {', '.join(sorted(repo_lang_hints))}")

if __name__ == "__main__":
    app()