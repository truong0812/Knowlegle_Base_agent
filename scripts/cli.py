#!/usr/bin/env python3
"""
Knowledge Base Agent CLI.
Converts codebase into structured knowledge base (JSON entries + FAISS index).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

import typer

app = typer.Typer(help="Knowledge Base Agent — codebase → structured KB")


@app.command()
def scan(
    repo: Path = typer.Option(Path("."), help="Path to repository"),
    out: Path = typer.Option(Path(".kb"), help="Output directory"),
) -> None:
    """Scan repository and produce file manifest (.kb/manifest.json)."""
    repo = repo.resolve()
    out = out.resolve()

    # TODO: implement scanner
    typer.echo(f"Scanning {repo} → {out}")
    typer.echo("Not implemented yet. See docs/MVP.md for roadmap.")


@app.command()
def parse(
    repo: Path = typer.Option(Path("."), help="Path to repository"),
    manifest: Path = typer.Option(Path(".kb/manifest.json"), help="File manifest"),
    out: Path = typer.Option(Path(".kb"), help="Output directory"),
) -> None:
    """Parse source files using tree-sitter, extract symbols."""
    # TODO: implement tree-sitter parser (M1)
    typer.echo("Not implemented yet.")


@app.command()
def analyze(
    repo: Path = typer.Option(Path("."), help="Path to repository"),
    out: Path = typer.Option(Path(".kb"), help="Output directory"),
) -> None:
    """Run full 3-layer analysis pipeline (scan → parse → analyze)."""
    # TODO: implement layered pipeline (M2)
    typer.echo("Not implemented yet.")


@app.command()
def validate(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Validate KB quality: consistency, coverage, accuracy."""
    # TODO: implement validator (M3)
    typer.echo("Not implemented yet.")


@app.command()
def query(
    question: str = typer.Argument(help="Question to ask about the codebase"),
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Query the knowledge base using semantic search."""
    # TODO: implement QA endpoint (M4)
    typer.echo("Not implemented yet.")


if __name__ == "__main__":
    app()
