# Current Status

Updated: 2026-05-16

## Summary

Knowledge Base Agent is in a working graph-aware MVP state with the first Phase 2 "Confident Graph" slice implemented. The codebase supports both the original layered KB pipeline and the newer graph-aware pipeline. The graph-aware path is the preferred path for new snapshots because it produces a symbol graph, materialized retrieval views, feature overlays, and graph-aware retrieval context.

## Verified Health

```text
pytest -q
193 passed, 3 dependency warnings
```

The warnings are SWIG/native dependency deprecation warnings surfaced during analyzer tests; they are not Phase 2 logic failures.

The working tree currently contains uncommitted Phase 2 implementation updates.

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
- `feature`

Expected graph files:

- `.kb/graph/nodes.jsonl`
- `.kb/graph/edges.jsonl`
- `.kb/graph/adjacency.json`
- `.kb/graph/features.jsonl` when deterministic feature clusters are found

Latest documented rebuilt snapshot:

- Total entries: 521
- Layers: `arch: 1`, `mod: 24`, `file: 50`, `mem: 446`
- Index files: `.kb/index/faiss.index`, `.kb/index/id_map.json`
- Validation: 100% consistency, no orphan entries
- Graph-aware query smoke test: `RetrievalEngine` returns primary results, related nodes, 2-hop context, and relationship edges

Note: the stats above predate the Phase 2 feature layer changes. Rebuild `.kb/` before treating snapshot counts as current.

## Canonical Runtime Model

```text
Parser output
  -> Symbol graph
  -> Materialized KB views + deterministic feature overlay
  -> FAISS index
  -> Intent-planned graph-aware retrieval
```

The symbol graph is the source of truth. KB entries are cached views designed for agent retrieval.

## Known Gaps

- `.kb/` is generated and ignored by Git.
- `Knowledge/Knowlegle_Base_agent/` is tracked but comes from a different snapshot toolchain.
- The KB writer does not prune stale entry files, so clean graph snapshots should remove `.kb/` before rebuild.
- Most docs are now aligned with graph-aware MVP status, but the long roadmap remains intentionally broad and should be treated as strategy, not an exact implementation tracker.

## Retrieval Benchmark Baseline

Phase 2 has deterministic retrieval benchmark coverage in `tests/test_retrieval_benchmarks.py`.

Current gold query coverage:

- `symbol_lookup`: `What does RetrievalEngine do?`
- `flow_trace`: `How does graph retrieval work?`
- `module_overview`: `overview of query module`
- `relationship`: `Who calls compose_context?`

The benchmark mocks semantic seed search and verifies graph-aware retrieval behavior after seeds are selected: intent classification, entry-to-node mapping, graph expansion, context composition, and relationship output.

## Phase 2 Progress

Phase 2 implementation now includes:

- Python import alias metadata is captured in `ImportInfo.aliases`.
- GraphBuilder resolves aliased calls such as `from src.utils import helper as h; h()` into `aliased_import` call edges.
- `aliased_import` is now treated as a resolved heuristic edge with confidence `0.70`.
- Parser-level assignment extraction captures simple receiver assignments such as `svc = get_service()`.
- GraphBuilder resolves type-inferred receiver calls such as `svc.login()` when the assigned factory function has a return type that maps to a known class.
- Inherited `self.method()` calls resolve through base-class chains with `inherited_scope` confidence.
- Decorators are normalized, including `@inject` and qualified forms such as `@container.inject()`, so dependency-injected targets get confidence capped.
- Node confidence is propagated from high-confidence incoming edges.
- Query-time edge confidence decays by graph hop using the farthest endpoint, including incoming relationship traversal.
- Deterministic feature clusters are extracted from shared nouns and graph density, persisted to `features.jsonl`, and materialized as `feature` KB entries.
- QueryPlanner selects expansion strategy by intent: symbol lookup, flow trace, module overview, relationship, and default.

## Next Best Action

Rebuild a clean `.kb/` graph snapshot, validate it, and update snapshot stats after the Phase 2 feature layer is materialized.
