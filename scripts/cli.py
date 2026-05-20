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
    federated: bool = typer.Option(False, help="Enable cross-repo federation"),
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
        federated=federated,
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


@app.command()
def ingest_telemetry(
    traces_file: Path = typer.Argument(help="JSON file with trace spans"),
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Ingest OpenTelemetry traces and map to symbol graph nodes."""
    import json as json_mod
    from kb_agent.graph.storage import GraphStorage
    from kb_agent.graph.telemetry import TelemetryIngestor, TelemetryStorage
    from kb_agent.models.telemetry import TraceSpan

    kb = kb.resolve()
    graph_dir = kb / "graph"
    if not graph_dir.exists():
        typer.echo("Error: No graph found. Run `analyze --with-graph` first.", err=True)
        raise typer.Exit(1)

    traces_data = json_mod.loads(traces_file.read_text(encoding="utf-8"))
    if isinstance(traces_data, dict):
        traces_data = traces_data.get("spans", [traces_data])
    spans = [TraceSpan(**s) for s in traces_data]

    nodes, edges = GraphStorage(graph_dir).load()
    ingestor = TelemetryIngestor(nodes, edges)
    mapped = ingestor.ingest_traces(spans)

    tel_storage = TelemetryStorage(kb / "telemetry")
    tel_storage.save_traces(mapped)

    mapped_count = sum(1 for s in mapped if s.mapped_node_id)
    typer.echo(f"Ingested {len(spans)} spans, mapped {mapped_count} to graph nodes")


@app.command()
def update_runtime_metadata(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Re-compute runtime metadata from ingested traces."""
    from kb_agent.graph.telemetry import TelemetryIngestor, TelemetryStorage

    kb = kb.resolve()
    tel_storage = TelemetryStorage(kb / "telemetry")
    spans = tel_storage.load_traces()
    if not spans:
        typer.echo("No traces found. Run `ingest-telemetry` first.")
        raise typer.Exit(1)

    from kb_agent.graph.storage import GraphStorage
    nodes, edges = GraphStorage(kb / "graph").load()
    ingestor = TelemetryIngestor(nodes, edges)
    metadata = ingestor.compute_runtime_metadata(spans)
    tel_storage.save_runtime_metadata(metadata)
    typer.echo(f"Updated runtime metadata for {len(metadata)} nodes")


@app.command()
def train_ranking_model(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
    min_samples: int = typer.Option(20, help="Minimum feedback samples required"),
) -> None:
    """Train retrieval ranking model from collected feedback."""
    from kb_agent.graph.telemetry import TelemetryStorage
    from kb_agent.query.self_tuning import SelfTuningRetrieval

    kb = kb.resolve()
    tel_storage = TelemetryStorage(kb / "telemetry")
    tuner = SelfTuningRetrieval(tel_storage, kb / "graph")
    config = tuner.train_ranking_model(min_samples=min_samples)
    if config is None:
        typer.echo("Insufficient feedback data for training.")
        raise typer.Exit(1)
    tel_storage.save_tuning_config(config)
    typer.echo(f"Model trained: accuracy={config.accuracy:.2%}, samples={config.sample_count}")


@app.command()
def auto_tune(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Auto-tune retrieval parameters from trained model."""
    from kb_agent.graph.telemetry import TelemetryStorage
    from kb_agent.query.self_tuning import SelfTuningRetrieval

    kb = kb.resolve()
    tel_storage = TelemetryStorage(kb / "telemetry")
    config = tel_storage.load_tuning_config()
    if config is None:
        typer.echo("No tuning config found. Run `train-ranking-model` first.")
        raise typer.Exit(1)

    tuner = SelfTuningRetrieval(tel_storage, kb / "graph")
    tuner.auto_tune_parameters(config)
    typer.echo("Auto-tuning applied.")


@app.command()
def show_tuning_stats(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Show self-tuning statistics and active overrides."""
    from kb_agent.graph.telemetry import TelemetryStorage
    from kb_agent.query.self_tuning import SelfTuningRetrieval

    kb = kb.resolve()
    tel_storage = TelemetryStorage(kb / "telemetry")
    tuner = SelfTuningRetrieval(tel_storage, kb / "graph")
    stats = tuner.get_tuning_stats()
    typer.echo(f"Feedback total: {stats['feedback_total']}")
    typer.echo(f"Useful rate: {stats['useful_rate']:.1%}")
    typer.echo(f"Last accuracy: {stats['accuracy']:.1%}")
    if stats['active_overrides']:
        typer.echo(f"Active overrides: {stats['active_overrides']}")


@app.command()
def add_repo(
    repo_path: str = typer.Argument(help="Path to the other repo's .kb directory"),
    name: str = typer.Option(None, help="Human-readable name for the repo"),
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Register an external repository for cross-repo symbol resolution."""
    from kb_agent.graph.federation import FederatedGraphManager

    kb = kb.resolve()
    fed = FederatedGraphManager(kb)
    ref = fed.add_repository(repo_path, repo_name=name)
    typer.echo(f"Registered repository: {ref.repo_name} ({ref.node_count} nodes, {ref.edge_count} edges)")


@app.command()
def resolve_cross_repo(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Resolve cross-repository symbol references and persist to graph."""
    from kb_agent.graph.federation import FederatedGraphManager
    from kb_agent.graph.storage import GraphStorage

    kb = kb.resolve()
    graph_dir = kb / "graph"
    storage = GraphStorage(graph_dir)
    nodes, edges = storage.load()

    fed = FederatedGraphManager(kb)
    result = fed.resolve_cross_repo_symbols(nodes, edges)

    if result.edges:
        # Add foreign nodes so retrieval expander can traverse REFERENCES_REPO edges
        all_nodes = nodes + result.foreign_nodes
        all_edges = edges + result.edges
        storage.save(all_nodes, all_edges)
        typer.echo(
            f"Resolved {len(result.edges)} cross-repo references, "
            f"imported {len(result.foreign_nodes)} foreign nodes"
        )
    else:
        typer.echo("Found 0 cross-repo references")


@app.command()
def update_shared_deps(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Update shared dependency references across registered repos."""
    from kb_agent.graph.federation import FederatedGraphManager

    kb = kb.resolve()
    fed = FederatedGraphManager(kb)
    refs = fed.update_shared_deps()
    typer.echo(f"Updated {len(refs)} shared dependency references")


@app.command()
def dashboard(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Show observability dashboard with graph health and retrieval analytics."""
    from kb_agent.analyzer.dashboard import DashboardAnalyzer

    kb = kb.resolve()
    analyzer = DashboardAnalyzer(kb)
    health = analyzer.graph_health()
    analytics = analyzer.retrieval_analytics()
    typer.echo(DashboardAnalyzer.format_health(health))
    typer.echo()
    typer.echo(DashboardAnalyzer.format_analytics(analytics))


@app.command()
def graph_health(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Show graph health metrics."""
    from kb_agent.analyzer.dashboard import DashboardAnalyzer

    kb = kb.resolve()
    analyzer = DashboardAnalyzer(kb)
    health = analyzer.graph_health()
    typer.echo(DashboardAnalyzer.format_health(health))


@app.command()
def query_analytics(
    kb: Path = typer.Option(Path(".kb"), help="Knowledge base directory"),
) -> None:
    """Show retrieval analytics."""
    from kb_agent.analyzer.dashboard import DashboardAnalyzer

    kb = kb.resolve()
    analyzer = DashboardAnalyzer(kb)
    analytics = analyzer.retrieval_analytics()
    typer.echo(DashboardAnalyzer.format_analytics(analytics))


if __name__ == "__main__":
    app()
