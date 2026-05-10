#!/usr/bin/env python3
# language: python
"""
MD Generator for KB-Agent (MVP).
- Reads .kb/artifacts/chunks/chunks_index.json and per-chunk JSON files.
- Renders Markdown files under docs/kb/{classes,methods,functions}.
Run:
  python scripts/generate_md.py --chunks .kb/artifacts/chunks --out docs/kb
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Any
import typer
import datetime

app = typer.Typer(help="Generate Markdown from chunk sidecars")

def render_front_matter(meta: Dict[str, Any]) -> str:
    lines = ["---"]
    for k in ("id", "kind", "language", "path", "signature", "summary", "tags", "source_commit", "tests", "confidence"):
        if k in meta and meta[k] is not None:
            val = meta[k]
            if isinstance(val, (list, dict)):
                # simple list/dict rendering
                import yaml
                lines.append(f"{k}: {yaml.safe_dump(val, default_flow_style=True).strip()}")
            elif isinstance(val, str):
                lines.append(f'{k}: "{val.replace(chr(34), "\\\"")}"')
            else:
                lines.append(f"{k}: {val}")
    lines.append("---")
    return "\n".join(lines)

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

@app.command()
def run(chunks: Path = typer.Option(Path(".kb/artifacts/chunks"), help="Chunks dir"),
        out: Path = typer.Option(Path("docs/kb"), help="Output docs dir")):
    chunks = chunks.resolve()
    out = out.resolve()
    index_file = chunks / "chunks_index.json"
    if not index_file.exists():
        typer.echo(f"Missing {index_file}. Run extractor first.")
        raise typer.Exit(code=1)

    try:
        with index_file.open("r", encoding="utf-8") as fh:
            index = json.load(fh)
    except Exception as e:
        typer.echo(f"Failed to read index: {e}")
        raise typer.Exit(code=1)

    # prepare output dirs
    classes_dir = out / "classes"
    methods_dir = out / "methods"
    functions_dir = out / "functions"
    ensure_dir(classes_dir)
    ensure_dir(methods_dir)
    ensure_dir(functions_dir)

    written = 0
    for item in index:
        fid = item.get("id")
        fpath = Path(item.get("file"))
        kind = item.get("kind", "unknown")
        if not fid or not fpath.exists():
            continue
        try:
            with fpath.open("r", encoding="utf-8") as fh:
                chunk = json.load(fh)
        except Exception:
            continue

        meta = {
            "id": chunk.get("id"),
            "kind": chunk.get("kind"),
            "language": chunk.get("language"),
            "path": chunk.get("path"),
            "signature": chunk.get("signature"),
            "summary": chunk.get("docstring") or "",
            "tags": chunk.get("tags", []),
            "source_commit": chunk.get("source_commit", None),
            "tests": chunk.get("tests", []),
            "confidence": chunk.get("confidence", 0.0),
        }

        body_lines = []
        # docstring / summary
        if chunk.get("docstring"):
            body_lines.append("## Docstring\n")
            body_lines.append(chunk["docstring"].strip() + "\n")
        # source snippet
        if chunk.get("src_snippet"):
            body_lines.append("## Source\n")
            body_lines.append("```python\n" + chunk["src_snippet"].rstrip() + "\n```\n")
        # links / provenance
        if chunk.get("links"):
            body_lines.append("## Links\n")
            for k, v in chunk["links"].items():
                body_lines.append(f"- {k}: {v}")
            body_lines.append("")
        # parse evidence
        if chunk.get("parse_evidence"):
            body_lines.append("## Parse evidence\n")
            for ev in chunk["parse_evidence"]:
                body_lines.append(f"- {ev.get('parser')} ok={ev.get('ok')}")
            body_lines.append("")

        # default filename by kind
        if kind == "class":
            out_file = classes_dir / f"{fid}.md"
        elif kind == "method":
            out_file = methods_dir / f"{fid}.md"
        elif kind == "function":
            out_file = functions_dir / f"{fid}.md"
        else:
            out_file = out / f"{fid}.md"

        # attempt to build front-matter (use PyYAML if available)
        try:
            fm = render_front_matter(meta)
        except Exception:
            # minimal fallback
            fm = "---\n" + f"id: {meta['id']}\nkind: {meta['kind']}\n---"

        content = fm + "\n\n" + "\n".join(body_lines)
        try:
            with out_file.open("w", encoding="utf-8") as fh:
                fh.write(content)
            written += 1
        except Exception:
            continue

    typer.echo(f"Wrote {written} markdown files to {out}")
    typer.echo(f"Generated at {datetime.datetime.utcnow().isoformat()}Z")

if __name__ == "__main__":
    app()