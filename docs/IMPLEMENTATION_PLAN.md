# Implementation Plan

Updated: 2026-05-16

## Current Baseline

The MVP is complete and currently passes the full test suite:

```text
193 passed, 3 dependency warnings
```

The warnings are SWIG/native dependency deprecation warnings surfaced by analyzer/indexing dependencies, not project logic failures.

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
| Tests | Done | 193 tests passing |
| Retrieval benchmarks | Done | Deterministic gold queries for Phase 2 retrieval precision |
| Phase 2 symbol resolution | Done | Import aliases, inherited calls, type-inferred receiver calls, decorator confidence rules |
| Phase 2 confidence | Done | Node confidence propagation and query-time hop decay |
| Phase 2 feature overlay | Done | Deterministic noun/graph-density clusters materialized as `feature` entries |
| Phase 2 query planner | Done | Intent-based expansion strategies for graph retrieval |

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

Note: these snapshot stats predate the Phase 2 `feature` layer. Rebuild `.kb/` before using counts as current.

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

Phase 2 improves retrieval precision without adding unnecessary product surface. The initial implementation slice is now complete in code and tests.

Completed Phase 2 scope:

1. Enhanced symbol resolution.
   - Python import aliases resolve to `aliased_import`.
   - Inherited `self.method()` calls resolve through base-class chains.
   - Simple receiver calls resolve through assignment plus return-type inference.
   - Decorator names are normalized and dependency-injected targets get capped confidence.

2. Confidence propagation.
   - Node confidence is boosted by multiple high-confidence incoming edges.
   - Query-time edge confidence decays by graph distance, including incoming traversal.

3. Deterministic feature overlay.
   - Symbols are clustered by shared nouns and graph density.
   - Features are persisted in graph storage and materialized as `feature` entries.

4. Query planner and benchmarks.
   - Intent classification selects expansion strategies for symbol lookup, flow trace, module overview, relationship, and default.
   - Benchmarks measure retrieval behavior with expected node IDs and relationship output.

## Acceptance Criteria For Phase 2

| Metric | Target |
|---|---:|
| Test suite | 193 passing |
| Alias resolution tests | Implemented |
| Inherited call resolution | Implemented |
| Type-inferred receiver calls | Implemented for simple assignment + return type chains |
| Feature overlay repeatability | Same feature IDs across repeated runs |
| Retrieval benchmark | Gold queries assert expected graph behavior |

## Next Phase 2 Hardening

- Rebuild and validate a fresh `.kb/` snapshot with the `feature` layer.
- Add ambiguity tests for duplicate return-type factory names across files.
- Extend type inference beyond simple `name = function()` assignments only when it stays deterministic.
- Decide whether dependency warning filters belong in test config after dependency review.
- Measure retrieval benchmark deltas after snapshot rebuild.

## Near-Term Maintenance

- Keep README and this tracker aligned with actual test count and CLI behavior.
- Prefer graph-mode snapshots for demos and agent use.
- Avoid committing generated `.kb/` output unless snapshot policy changes.
- Add a cleanup step or overwrite mode to `AnalysisPipeline` so stale entries cannot survive mode changes.
- Keep entry filename serialization centralized; writer and query loader now share the same filesystem-safe filename helper.
