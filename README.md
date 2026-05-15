# Knowledge Base Agent

Knowledge Base Agent turns a source repository into a structured, queryable knowledge base for other AI agents. The project is built around a deterministic-first pipeline: parse source code, build a symbol graph, materialize useful KB views, then use embeddings and graph expansion for retrieval.

## Current Status

MVP is implemented and tested.

- Scanner and language detection for Python, C#, and C++.
- Tree-sitter based parsers, with Python AST fallback.
- Legacy layered analysis: `arch`, `mod`, `mem`.
- Graph-aware analysis: symbol graph plus `arch`, `mod`, `file`, and `mem` materialized views.
- FAISS semantic index and graph-aware retrieval.
- CLI commands for scan, parse, analyze, validate, index, and query.
- Test suite status on 2026-05-15: `129 passed`.

The graph path is the recommended path for new snapshots:

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2
python -m scripts.cli validate --kb .kb
python -m scripts.cli query "How does retrieval work?" --kb .kb --with-graph
```

Latest local graph snapshot, rebuilt on 2026-05-15:

- 521 KB entries
- Layers: `arch: 1`, `mod: 24`, `file: 50`, `mem: 446`
- Graph files: `nodes.jsonl`, `edges.jsonl`, `adjacency.json`
- Index files: `faiss.index`, `id_map.json`
- Validation: parent consistency and orphan detection pass

## Architecture

The system has two compatible analysis modes.

### Legacy Layered Analysis

```text
Repository
  -> scanner
  -> parsers
  -> architecture layer
  -> module layer
  -> member layer
  -> KB entries + FAISS index
```

This path is still supported and is useful as a simple fallback.

### Graph-Aware Analysis

```text
Repository
  -> scanner
  -> parsers
  -> symbol graph
  -> materialized views
     -> ARCH view
     -> MOD view
     -> FILE view
     -> MEM view
  -> KB entries + FAISS index
  -> graph-aware retrieval
```

The symbol graph is the source of truth. KB entries are materialized views optimized for retrieval and agent context.

## Installation

Requires Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Optional query dependencies are listed in `requirements.txt`:

- `sentence-transformers`
- `faiss-cpu`

## CLI Usage

### Scan

```bash
python -m scripts.cli scan --repo .
```

Lists supported source files and detected languages.

### Parse

```bash
python -m scripts.cli parse --repo .
```

Prints extracted symbols and imports.

### Analyze

Static-only legacy snapshot:

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai
```

Static-only graph snapshot:

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2
```

LLM enrichment can be enabled by omitting `--skip-ai` and setting `OPENAI_API_KEY`.

### Validate

```bash
python -m scripts.cli validate --kb .kb
```

Checks parent consistency and orphan entries.

### Query

Flat semantic search:

```bash
python -m scripts.cli query "What does the parser do?" --kb .kb
```

Graph-aware retrieval:

```bash
python -m scripts.cli query "How does graph retrieval expand context?" --kb .kb --with-graph
```

## Output Layout

```text
.kb/
  entries/               JSON KB entries
  graph/                 nodes, edges, adjacency data when --with-graph is used
  index/                 FAISS index and ID map
  manifest.json          snapshot metadata
  quality_report.json    validation report
```

In graph mode, `entries/` contains four view layers:

- `arch`: repository overview
- `mod`: module-level views grouped by `--depth`
- `file`: file-level symbol and dependency views
- `mem`: class/function/member-level views

## Project Direction

The next development phase is Phase 2: Confident Graph.

Recommended order:

1. Enhanced symbol resolution.
2. Confidence propagation.
3. Deterministic feature overlay.
4. Basic query planner and retrieval benchmarks.

See [docs/mvp_and_roadmap.md](docs/mvp_and_roadmap.md) for the longer roadmap.
