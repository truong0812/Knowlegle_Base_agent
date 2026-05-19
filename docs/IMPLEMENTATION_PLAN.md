# Implementation Plan

Updated: 2026-05-19

## Current Baseline

Phase 3 "Intelligent Retrieval" is now complete. The test suite passes:

```text
257 passed, 3 dependency warnings
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
| CLI | Done | `scan`, `parse`, `analyze`, `validate`, `index`, `query`, `versions`, `diff` |
| Tests | Done | 257 tests passing |
| Retrieval benchmarks | Done | Deterministic gold queries for retrieval precision |
| Phase 2 symbol resolution | Done | Import aliases, inherited calls, type-inferred receiver calls, decorator confidence rules |
| Phase 2 confidence | Done | Node confidence propagation and query-time hop decay |
| Phase 2 feature overlay | Done | Deterministic noun/graph-density clusters materialized as `feature` entries |
| Phase 2 query planner | Done | Intent-based expansion strategies for graph retrieval |
| Phase 3 hot-path | Done | Incoming call frequency scoring, persisted to hotpath.json |
| Phase 3 graph embeddings | Done | Graph-aware text enrichment for MEM entry embeddings |
| Phase 3 temporal graph | Done | Versioned snapshots at commit boundaries, diff command |
| Phase 3 chain detection | Done | Causal chain tracing with CHAIN_TRACE intent |
| Phase 3 cross-language bridge | Done | HTTP API, data contract, message queue bridge strategies |

## Phase 3 File Manifest

### New Files (12)
| File | Purpose |
|---|---|
| `kb_agent/graph/hotpath.py` | Hot-path scoring |
| `kb_agent/graph/temporal.py` | Versioned snapshot management |
| `kb_agent/graph/bridge.py` | Cross-language bridge detection |
| `kb_agent/indexer/graph_embedding.py` | Graph-aware embedding text builder |
| `kb_agent/models/temporal.py` | Temporal graph models |
| `kb_agent/query/chain.py` | Causal chain detection |
| `kb_agent/query/temporal_query.py` | Temporal query handler |
| `tests/test_hotpath.py` | 11 tests |
| `tests/test_graph_embedding.py` | 10 tests |
| `tests/test_temporal.py` | 14 tests |
| `tests/test_chain.py` | 11 tests |
| `tests/test_bridge.py` | 15 tests |

### Modified Files (12)
| File | Changes |
|---|---|
| `kb_agent/models/graph.py` | Added `BRIDGES_TO` EdgeKind, `bridge_metadata` field |
| `kb_agent/graph/builder.py` | Added `detect_bridges` param, `_detect_cross_language_bridges()` |
| `kb_agent/graph/storage.py` | Added `save_hotpath()`, `load_hotpath()` |
| `kb_agent/graph/confidence.py` | Added `BRIDGE_CONFIDENCE_RANGES` |
| `kb_agent/indexer/indexer.py` | Accept `graph_dir` for enriched embeddings |
| `kb_agent/query/intent.py` | Added `CHAIN_TRACE`, `VERSION_DIFF` intents |
| `kb_agent/query/planner.py` | Added strategies for new intents |
| `kb_agent/query/expander.py` | Added `hop4_nodes`, BRIDGES_TO edge passthrough |
| `kb_agent/query/composer.py` | Hot-path ranking, chain tier, hop4 tier, bridge formatting |
| `kb_agent/query/retrieval.py` | Hot-path loading, chain detection integration |
| `kb_agent/analyzer/pipeline.py` | Hot-path, temporal snapshot, bridge detection, graph-aware indexing |
| `scripts/cli.py` | `versions`, `diff` commands; `--detect-bridges`, `--with-graph`, `--version-id` flags |

## Recommended Snapshot Command (Phase 3)

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2 --detect-bridges
python -m scripts.cli validate --kb .kb
python -m scripts.cli versions --kb .kb
```

## Next Phase: Phase 4 — Production Intelligence

Phase 4 brings runtime and operational intelligence into the graph:

- OpenTelemetry/runtime trace integration
- Latency, error rate, call-frequency metadata
- Multi-repository federated graphs
- Retrieval observability dashboard
- Self-tuning ranking algorithms
