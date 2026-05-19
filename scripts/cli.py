#!/usr/bin/env python3
"""
Knowledge Base Agent CLI.
Converts codebase into structured knowledge base (JSON entries + FAISS index).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer

app = typer.Typer(help="Knowledge Base Agent — codebase → structured KB")


@app.command()
def scan(
    repo: Path = typer.Option(Path("."), help="Path to repository"),
    out: Path = typer.Option(Path(".kb"), help="Output directory"),
) -> None:
    """Scan repository and list source files with language detection."""
    from kb_agent.scanner.scanner import FileScanner

    repo = repo.resolve()
    scanner = FileScanner(repo)
    entries = scanner.scan()

    typer.echo(f"Found {len(entries)} source files in {repo}")
    for entry in entries:
        typer.echo(f"  {entry.language.value:8s} {entry.path}")


@app.command()
def parse(
    repo: Path = typer.Option(Path("."), help="Path to repository"),
) -> None:
    """Parse source files using tree-sitter and show extracted symbols."""
    from kb_agent.scanner.scanner import FileScanner
    from kb_agent.parser.factory import get_parser

    repo = repo.resolve()
    scanner = FileScanner(repo)
    file_entries = scanner.scan()

    for fe in file_entries:
        source = (repo / fe.path).read_bytes()
        parser = get_parser(fe.language)
        result = parser.parse_file(source, fe.path)

        typer.echo(f"\n{fe.path} ({fe.language.value}):")
        if result.errors:
            for err in result.errors:
                typer.echo(f"  ERROR: {err}")
        for sym in result.symbols:
            typer.echo(f"  {sym.kind.value:10s} L{sym.line_start:>3d}-{sym.line_end:<3d} {sym.name}")
            if sym.signature:
                typer.echo(f"             {sym.signature}")
        for imp in result.imports:
            names = ", ".join(imp.imported_names) if imp.imported_names else "*"
            typer.echo(f"  import     {imp.module_path} ({names})")


@app.command()
def analyze(
    repo: Path = typer.Option(Path("."), help="Path to repository"),
    out: Path = typer.Option(Path(".kb"), help="Output directory"),
    skip_ai: bool = typer.Option(False, help="Skip LLM analysis (static only)"),
    with_graph: bool = typer.Option(False, help="Build symbol graph with edge resolution"),
    depth: int = typer.Option(1, help="Module grouping depth (1=src/, 2=src/services/)"),
    model: str = typer.Option("gpt-4o", help="LLM model name"),
    version_id: str = typer.Option(None, help="Version label for temporal snapshot"),
    detect_bridges: bool = typer.Option(False, help="Detect cross-language bridges"),
) -> None:
    """Run full 3-layer analysis pipeline (scan → parse → analyze)."""
    from kb_agent.analyzer.llm import LLMClient
    from kb_agent.analyzer.pipeline import AnalysisPipeline

    repo = repo.resolve()
    out = out.resolve()

    llm_client = None if skip_ai else LLMClient(model=model, cache_dir=out / ".cache")
    pipeline = AnalysisPipeline(
        repo_root=repo, out_dir=out, llm_client=llm_client,
        build_graph=with_graph, module_depth=depth,
        version_id=version_id, detect_bridges=detect_bridges,
    )
    manifest = asyncio.run(pipeline.run())

    typer.echo(f"Analysis complete: {manifest.stats.total_entries} entries")
    typer.echo(f"  Layers: {manifest.stats.by_layer}")
    typer.echo(f"  Languages: {', '.join(manifest.languages)}")
    typer.echo(f"  Output: {out}")


@app.command()
def validate(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Validate KB quality: consistency, coverage, accuracy."""
    from kb_agent.validator.validator import KBValidator

    kb = kb.resolve()
    validator = KBValidator(kb)
    report = validator.validate()

    typer.echo(f"Validation report for {kb}:")
    typer.echo(f"  Total entries: {report.total_entries}")
    typer.echo(f"  Consistency: {report.consistency:.0%}")
    for check in report.checks:
        status = "PASS" if check.passed else "FAIL"
        typer.echo(f"  [{status}] {check.name}: {check.details}")
    if report.low_confidence_entries:
        typer.echo(f"  Low confidence ({len(report.low_confidence_entries)}): {report.low_confidence_entries[:5]}")


@app.command()
def index(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
    model: str = typer.Option("all-MiniLM-L6-v2", help="Embedding model name"),
    with_graph: bool = typer.Option(False, help="Enrich embeddings with graph context"),
) -> None:
    """Build or rebuild the FAISS vector index from existing KB entries."""
    from kb_agent.indexer.indexer import KBIndexer
    from kb_agent.validator.validator import KBValidator

    kb = kb.resolve()
    entries = KBValidator(kb)._load_entries()

    if not entries:
        typer.echo("No entries found. Run `analyze` first.")
        raise typer.Exit(1)

    graph_dir = kb / "graph" if with_graph else None
    indexer = KBIndexer(model_name=model)
    indexer.build_index(entries, kb / "index", graph_dir=graph_dir)
    typer.echo(f"Indexed {len(entries)} entries -> {kb / 'index'}")


@app.command()
def query(
    question: str = typer.Argument(help="Question to ask about the codebase"),
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
    top_k: int = typer.Option(5, help="Number of results"),
    with_graph: bool = typer.Option(False, help="Use graph-aware retrieval"),
) -> None:
    """Query the knowledge base using semantic search."""
    kb = kb.resolve()

    if with_graph:
        from kb_agent.query.retrieval import RetrievalEngine

        engine = RetrievalEngine(kb)
        try:
            result = engine.retrieve(question, top_k=top_k)
        except FileNotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

        typer.echo(result.context)
        if result.metrics.truncated:
            typer.echo(f"\n[Truncated {len(result.metrics.truncated_nodes)} nodes]")
    else:
        from kb_agent.query.engine import QueryEngine

        engine = QueryEngine(kb)
        try:
            results = engine.query(question, top_k=top_k)
        except FileNotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

        typer.echo(f"Top {len(results)} results for: '{question}'\n")
        for entry in results:
            typer.echo(f"[{entry.layer.value}] {entry.id}")
            if entry.static.signature:
                typer.echo(f"  {entry.static.signature}")
            if entry.ai.summary:
                typer.echo(f"  {entry.ai.summary}")
            typer.echo(f"  {entry.static.path}:{entry.static.line_start}")
            typer.echo()


@app.command()
def versions(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """List stored graph versions."""
    from kb_agent.graph.temporal import TemporalGraphManager

    kb = kb.resolve()
    manager = TemporalGraphManager(kb / "graph")
    version_list = manager.list_versions()
    if not version_list:
        typer.echo("No versions found.")
        return
    for v in version_list:
        commit = v.commit_hash[:8] if v.commit_hash else "n/a"
        parent = f" (parent: {v.parent_version})" if v.parent_version else ""
        typer.echo(f"  {v.version_id}  nodes={v.node_count}  edges={v.edge_count}  commit={commit}{parent}")


@app.command()
def diff(
    from_version: str = typer.Option(..., help="Source version ID"),
    to_version: str = typer.Option(..., help="Target version ID"),
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Show diff between two graph versions."""
    from kb_agent.graph.temporal import TemporalGraphManager
    from kb_agent.query.temporal_query import TemporalQueryHandler

    kb = kb.resolve()
    handler = TemporalQueryHandler(kb / "graph")
    version_diff = handler.diff_versions(from_version, to_version)
    typer.echo(TemporalQueryHandler.format_diff(version_diff))


if __name__ == "__main__":
    app()
