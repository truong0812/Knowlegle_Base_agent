#!/usr/bin/env python3
# language: python
"""
Python extractor (MVP).
- Reads .kb/artifacts/files.json
- For each file with language == 'python' it parses the AST and emits chunk sidecars into .kb/artifacts/chunks/
- Run: python scripts/extractors/python_extractor.py run --artifacts .kb/artifacts --out .kb/artifacts/chunks
"""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
import typer

app = typer.Typer(help="Python extractor for KB-Agent (MVP)")

ID_SAFE_RE = re.compile(r"[^0-9a-zA-Z_.-]+")


def make_id(text: str) -> str:
    return ID_SAFE_RE.sub("_", text)


def build_signature(fn: ast.FunctionDef) -> str:
    parts: List[str] = []
    args = fn.args
    # positional args
    for a in args.args:
        parts.append(a.arg)
    # vararg
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    # kwonly args
    for a in args.kwonlyargs:
        parts.append(a.arg)
    # kwarg
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    return f"def {fn.name}({', '.join(parts)})"


def read_source_segment(source_lines: List[str], start: int, end: Optional[int]) -> str:
    if start is None:
        return ""
    if end is None:
        end = start
    # AST lineno is 1-based
    return "".join(source_lines[start - 1:end])


@app.command()
def run(artifacts: Path = typer.Option(Path(".kb/artifacts"), help="Artifacts dir"),
        out: Path = typer.Option(Path(".kb/artifacts/chunks"), help="Chunks output dir")):
    artifacts = artifacts.resolve()
    out = out.resolve()
    files_json = artifacts / "files.json"
    if not files_json.exists():
        typer.echo(f"Missing {files_json}. Run scanner first.")
        raise typer.Exit(code=1)

    try:
        with files_json.open("r", encoding="utf-8") as fh:
            files = json.load(fh)
    except Exception as e:
        typer.echo(f"Failed to read {files_json}: {e}")
        raise typer.Exit(code=1)

    out.mkdir(parents=True, exist_ok=True)
    chunks_index: List[Dict] = []

    for entry in files:
        path = entry.get("path")
        lang = entry.get("language")
        if not path or lang != "python":
            continue
        abs_path = entry.get("abs_path")
        if not abs_path or not Path(abs_path).exists():
            continue

        try:
            with open(abs_path, "r", encoding="utf-8") as fh:
                src = fh.read()
            source_lines = src.splitlines(keepends=True)
            tree = ast.parse(src)
        except Exception as e:
            typer.echo(f"Parse failed for {path}: {e}")
            continue

        module_name = Path(path).with_suffix("").as_posix().replace("/", ".")
        # process module-level functions and classes
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                sig = build_signature(node)
                doc = ast.get_docstring(node) or ""
                start = getattr(node, "lineno", None)
                end = getattr(node, "end_lineno", None)
                src_snip = read_source_segment(source_lines, start, end)
                cid = make_id(f"{module_name}.{node.name}")
                chunk = {
                    "id": cid,
                    "kind": "function",
                    "language": "python",
                    "path": path,
                    "signature": sig,
                    "docstring": doc,
                    "src_snippet": src_snip,
                    "start_line": start,
                    "end_line": end,
                    "confidence": 0.95,
                    "parse_evidence": [{"type": "ast", "parser": "python-ast", "ok": True}],
                }
                fname = out / f"{cid}.json"
                with fname.open("w", encoding="utf-8") as fh:
                    json.dump(chunk, fh, ensure_ascii=False, indent=2)
                chunks_index.append({"id": cid, "file": str(fname), "kind": "function", "path": path})

            if isinstance(node, ast.ClassDef):
                class_doc = ast.get_docstring(node) or ""
                start = getattr(node, "lineno", None)
                end = getattr(node, "end_lineno", None)
                class_src = read_source_segment(source_lines, start, end)
                class_id = make_id(f"{module_name}.{node.name}")
                class_chunk = {
                    "id": class_id,
                    "kind": "class",
                    "language": "python",
                    "path": path,
                    "signature": f"class {node.name}",
                    "docstring": class_doc,
                    "src_snippet": class_src,
                    "start_line": start,
                    "end_line": end,
                    "confidence": 0.95,
                    "parse_evidence": [{"type": "ast", "parser": "python-ast", "ok": True}],
                }
                fname = out / f"{class_id}.json"
                with fname.open("w", encoding="utf-8") as fh:
                    json.dump(class_chunk, fh, ensure_ascii=False, indent=2)
                chunks_index.append({"id": class_id, "file": str(fname), "kind": "class", "path": path})

                # methods
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        sig = build_signature(item)
                        doc = ast.get_docstring(item) or ""
                        s = getattr(item, "lineno", None)
                        e = getattr(item, "end_lineno", None)
                        method_src = read_source_segment(source_lines, s, e)
                        mid = make_id(f"{module_name}.{node.name}.{item.name}")
                        mchunk = {
                            "id": mid,
                            "kind": "method",
                            "language": "python",
                            "path": path,
                            "signature": sig,
                            "docstring": doc,
                            "src_snippet": method_src,
                            "start_line": s,
                            "end_line": e,
                            "confidence": 0.95,
                            "parse_evidence": [{"type": "ast", "parser": "python-ast", "ok": True}],
                            "links": {"parent": f"../classes/{class_id}.md"}
                        }
                        mfname = out / f"{mid}.json"
                        with mfname.open("w", encoding="utf-8") as fh:
                            json.dump(mchunk, fh, ensure_ascii=False, indent=2)
                        chunks_index.append({"id": mid, "file": str(mfname), "kind": "method", "path": path})

    # write index
    index_file = out / "chunks_index.json"
    with index_file.open("w", encoding="utf-8") as fh:
        json.dump(chunks_index, fh, ensure_ascii=False, indent=2)

    typer.echo(f"Wrote {len(chunks_index)} chunk files to {out} and index {index_file}")


if __name__ == "__main__":
    app()