# Current Status

Updated: 2026-05-16

## Summary

Knowledge Base Agent is in a working MVP state. The codebase now supports both the original layered KB pipeline and the newer graph-aware pipeline. The graph-aware path is the preferred path for new snapshots because it produces a symbol graph and materialized retrieval views.

## Verified Health

```text
pytest -q
133 passed
```

Git working tree was clean before this documentation/snapshot update.

## Recommended Snapshot Command

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2
python -m scripts.cli validate --kb .kb
```

Expected graph-mode layers:

- `arch`
- `mod`
- `file`
- `mem`

Expected graph files:

- `.kb/graph/nodes.jsonl`
- `.kb/graph/edges.jsonl`
- `.kb/graph/adjacency.json`

Latest rebuilt snapshot:

- Total entries: 521
- Layers: `arch: 1`, `mod: 24`, `file: 50`, `mem: 446`
- Index files: `.kb/index/faiss.index`, `.kb/index/id_map.json`
- Validation: 100% consistency, no orphan entries
- Graph-aware query smoke test: `RetrievalEngine` returns primary results, related nodes, 2-hop context, and relationship edges

## Canonical Runtime Model

```text
Parser output
  -> Symbol graph
  -> Materialized KB views
  -> FAISS index
  -> Graph-aware retrieval
```

The symbol graph is the source of truth. KB entries are cached views designed for agent retrieval.

## Known Gaps

- `.kb/` is generated and ignored by Git.
- `Knowledge/Knowlegle_Base_agent/` is tracked but comes from a different snapshot toolchain.
- The KB writer does not prune stale entry files, so clean graph snapshots should remove `.kb/` before rebuild.
- Most docs are now aligned with graph-aware MVP status, but the long roadmap remains intentionally broad and should be treated as strategy, not an exact implementation tracker.

## Retrieval Benchmark Baseline

Phase 2 now has a deterministic retrieval benchmark baseline in `tests/test_retrieval_benchmarks.py`.

Current gold query coverage:

- `symbol_lookup`: `What does RetrievalEngine do?`
- `flow_trace`: `How does graph retrieval work?`
- `module_overview`: `overview of query module`
- `relationship`: `Who calls compose_context?`

The benchmark mocks semantic seed search and verifies graph-aware retrieval behavior after seeds are selected: intent classification, entry-to-node mapping, graph expansion, context composition, and relationship output.

## Next Best Action

Use the retrieval benchmark baseline to guide Phase 2 improvements: enhanced symbol resolution, confidence propagation, deterministic feature overlay, and query planner refinements.
