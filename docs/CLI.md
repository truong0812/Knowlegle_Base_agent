# CLI: scripts/cli.py

Purpose
- Scanner & language-detector for the MVP pipeline.
- Produces a machine-readable file list (.kb/artifacts/files.json) used by downstream extractors.

What it does
- Walks the repository (respects ignore patterns and .kbignore).
- Detects language per-file using extension, shebang, and repo manifest hints (e.g., .csproj, pyproject.toml).
- Emits per-file metadata: path, abs_path, size, language, confidence, evidence.

How to run (local)
1. Create venv and install dependencies:
```bash
# language: bash
python -m venv .venv
.venv\Scripts\activate
pip install typer
```
2. Run scanner:
```bash
# language: bash
python scripts/cli.py scan --repo /path/to/repo --out .kb/artifacts
```

Output example (.kb/artifacts/files.json)
```json
[
  {
    "path": "src/foo.py",
    "abs_path": "C:/.../repo/src/foo.py",
    "size": 1234,
    "language": "python",
    "confidence": 0.99,
    "evidence": [{"type":"extension","value":".py"}]
  },
  ...
]
```

Notes & next steps
- Use .kbignore at repo root to exclude files/paths.
- Intended as input to language-specific extractors (Python, C# for current scope).
- Next: create requirements.txt, add unit tests for detection heuristics, or run scan on a sample repo to validate results.