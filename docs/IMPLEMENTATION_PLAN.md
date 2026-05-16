# Implementation Plan

Updated: 2026-05-16

## Current Baseline

The MVP is complete and currently passes the full test suite:

```text
136 passed
```

The recommended operational path is graph-aware analysis:

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2
python -m scripts.cli validate --kb .kb
python -m scripts.cli query "How does retrieval work?" --kb .kb --with-graph
```

## Completed Work

| Area | Status | Notes |
|---|---:|---|
| Data models | Done | KB entries, manifests, reports, graph nodes, graph edges |
| Scanner | Done | Language detection, `.kbignore`, directory tree support |
| Parsers | Done | Python, C#, C++; calls, type usages, base classes |
| Legacy analysis | Done | `arch`, `mod`, `mem` layer pipeline |
| Symbol graph | Done | Stable path-based IDs, edge confidence metadata |
| Graph storage | Done | JSONL nodes/edges plus adjacency data |
| Materialized views | Done | `arch`, `mod`, `file`, `mem` views from graph |
| Indexer | Done | FAISS semantic index |
| Query engine | Done | Flat semantic query over KB entries |
| Graph retrieval | Done | Semantic seeds, bounded graph expansion, context composition |
| CLI | Done | `scan`, `parse`, `analyze`, `validate`, `index`, `query` |
| Tests | Done | 136 tests passing |
| Retrieval benchmarks | Started | Deterministic gold queries for Phase 2 retrieval precision |
| Phase 2 symbol resolution | Started | Python import aliases resolve to `aliased_import` call edges |

## Latest Graph Snapshot

Rebuilt locally on 2026-05-15 with:

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2
```

Snapshot stats:

| Metric | Value |
|---|---:|
| Total entries | 521 |
| `arch` entries | 1 |
| `mod` entries | 24 |
| `file` entries | 50 |
| `mem` entries | 446 |
| Validation consistency | 100% |

The snapshot includes both graph storage and FAISS index files.

## Important CLI Flags

| Command | Flag | Purpose |
|---|---|---|
| `analyze` | `--skip-ai` | Build deterministic/static KB without LLM calls |
| `analyze` | `--with-graph` | Build symbol graph and graph-derived materialized views |
| `analyze` | `--depth N` | Group module views by path depth |
| `query` | `--with-graph` | Use graph-aware retrieval instead of flat FAISS output |
| `query` | `--top-k N` | Number of semantic seed results |

## Current Snapshot Policy

`.kb/` is generated output and is ignored by Git. It should be regenerated from source when needed.

For a clean graph snapshot, remove the previous `.kb/` directory before running `analyze`; the writer appends/replaces individual entry files but does not prune stale files from older modes.

`Knowledge/Knowlegle_Base_agent/` is a separate tracked snapshot produced by a different project-understanding toolchain. Do not treat it as the canonical `.kb` output unless the team explicitly decides to migrate snapshot storage there.

## Next Phase: Confident Graph

Phase 2 should improve retrieval precision without adding unnecessary product surface.

Recommended order:

1. Enhanced symbol resolution.
   - Improve alias resolution. Initial Python import alias support is implemented.
   - Improve cross-file call target matching.
   - Add targeted tests for ambiguous calls and overload-like cases.

2. Confidence propagation.
   - Decay confidence by graph distance.
   - Boost nodes supported by multiple high-confidence edges.
   - Expose confidence in retrieval metrics.

3. Deterministic feature overlay.
   - Cluster symbols by shared nouns and graph density.
   - Keep feature generation deterministic and reproducible.

4. Query planner and benchmarks.
   - Baseline benchmark queries now cover symbol lookup, flow trace, module overview, and relationship lookup.
   - Measure retrieval quality with expected node IDs, not just text output.

## Acceptance Criteria For Phase 2

| Metric | Target |
|---|---:|
| Test suite | 100% passing |
| Alias resolution tests | >= 85% expected edges |
| Call resolution benchmark | >= 75% expected edges |
| Feature overlay repeatability | Same feature IDs across 3 runs |
| Retrieval benchmark | Top-5 contains expected node for each gold query |

## Near-Term Maintenance

- Keep README and this tracker aligned with actual test count and CLI behavior.
- Prefer graph-mode snapshots for demos and agent use.
- Avoid committing generated `.kb/` output unless snapshot policy changes.
- Add a cleanup step or overwrite mode to `AnalysisPipeline` so stale entries cannot survive mode changes.
- Keep entry filename serialization centralized; writer and query loader now share the same filesystem-safe filename helper.
