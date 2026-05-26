# Knowledge Base Agent — Lịch Sử Phát Triển

Updated: 2026-05-25

## Trạng Thái Hiện Tại

Knowledge Base Agent đã hoàn thành tất cả 5 phase. Test suite:

```text
pytest -q
320 passed, 3 dependency warnings
```

Warnings là SWIG/native dependency deprecation warnings, không phải project logic failures.

### Recommended Snapshot Command

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2 --detect-bridges
python -m scripts.cli validate --kb .kb
```

Expected graph-mode layers: `arch`, `mod`, `file`, `mem`, `feature`.

Expected graph files:

```text
.kb/graph/nodes.jsonl
.kb/graph/edges.jsonl
.kb/graph/adjacency.json
.kb/graph/features.jsonl
.kb/graph/hotpath.json
.kb/graph/versions/<version_id>/
```

---

## Phase 1: Graph-Aware MVP — Đã hoàn thành

Symbol Graph + Materialized Views + Basic Retrieval.

### Hạng mục bàn giao

| Thành phần | Status |
|---|---|
| Data models (SymbolNode, SymbolEdge, EdgeKind) | Done |
| Parser enhancements (calls, type usage, bases) — Python, C#, C++ | Done |
| Graph builder (7-phase build, 4 optimization indexes) | Done |
| Graph storage (JSONL + adjacency) | Done |
| Materialized views (ARCH/MOD/FILE/MEM) | Done |
| Retrieval engine (semantic + graph expansion) | Done |
| Pipeline integration (`--with-graph`, `--depth`) | Done |
| CLI (`scan`, `parse`, `analyze`, `validate`, `index`, `query`) | Done |

Test count lúc completion: 122

### Key Files

`kb_agent/models/graph.py`, `kb_agent/graph/builder.py`, `kb_agent/graph/storage.py`, `kb_agent/views/` (4 builders), `kb_agent/query/` (retrieval, expander, composer, intent, mapper), `kb_agent/parser/` (3 parsers), `scripts/cli.py`

---

## Phase 2: Confident Graph — Đã hoàn thành

Enhanced resolution, confidence propagation, feature overlay, query planner.

### Hạng mục bàn giao

| Thành phần | Status |
|---|---|
| Import alias resolution | Done |
| Inherited calls resolution | Done |
| Type-inferred receiver calls | Done |
| Decorator confidence rules | Done |
| Node confidence propagation + hop decay | Done |
| Deterministic feature overlay (noun/graph-density clusters) | Done |
| Intent-based query planner (4 intents) | Done |
| Retrieval benchmarks (deterministic gold queries) | Done |

Test count lúc completion: 172

### Key Files

`kb_agent/graph/resolver.py`, `kb_agent/graph/confidence.py`, `kb_agent/graph/features.py`, `kb_agent/query/planner.py`, `tests/test_retrieval_benchmarks.py`

---

## Phase 3: Intelligent Retrieval — Đã hoàn thành

Cross-language bridging, temporal graph, hot-path, graph-aware embeddings, chain detection.

### Hạng mục bàn giao

| Thành phần | Status |
|---|---|
| Hot-path prioritization (incoming CALLS edge count) | Done |
| Graph-aware embeddings (MEM entry enriched) | Done |
| Temporal graph (versioned snapshots at commit boundaries) | Done |
| Causal chain detection (CHAIN_TRACE intent) | Done |
| Cross-language bridging (HTTP, data contract, message queue) | Done |

Test count lúc completion: 257

### File Manifest

**New Files (12)**

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

**Modified Files (12)**

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

---

## Phase 4: Production Intelligence — Đã hoàn thành

Runtime telemetry, self-tuning retrieval, multi-repo federation, observability dashboard.

### Hạng mục bàn giao

| Thành phần | Status |
|---|---|
| OpenTelemetry trace ingestion (TelemetryIngestor + TelemetryStorage) | Done |
| Runtime metadata aggregation (call counts, latency, error rates) | Done |
| Self-tuning retrieval (heuristic ranking model, planner overrides) | Done |
| Multi-repo federation (namespaced foreign nodes, REFERENCES_REPO edges) | Done |
| Observability dashboard (graph health + retrieval analytics) | Done |

Test count lúc completion: 314

### File Manifest

**New/Modified Files (18)**

| File | Purpose |
|---|---|
| `kb_agent/graph/telemetry.py` | TelemetryIngestor + TelemetryStorage (214 lines) |
| `kb_agent/graph/federation.py` | FederatedGraphManager, cross-repo resolution (321 lines) |
| `kb_agent/query/self_tuning.py` | SelfTuningRetrieval, feedback-based tuning (116 lines) |
| `kb_agent/analyzer/dashboard.py` | Graph health + retrieval analytics dashboard (175 lines) |
| `kb_agent/models/telemetry.py` | Telemetry models (TraceSpan, etc.) |
| `kb_agent/models/federation.py` | Federation models |
| `kb_agent/models/dashboard.py` | Dashboard data models |
| `kb_agent/models/graph.py` | Added federation edge kinds |
| `kb_agent/query/expander.py` | Cross-repo node expansion |
| `kb_agent/query/planner.py` | Self-tuning planner overrides |
| `kb_agent/query/retrieval.py` | Self-tuning integration |
| `kb_agent/analyzer/pipeline.py` | Federation and telemetry pipeline hooks |
| `scripts/cli.py` | 8 new commands (ingest-telemetry, update-runtime-metadata, train-ranking-model, auto-tune, show-tuning-stats, add-repo, resolve-cross-repo, update-shared-deps, dashboard, graph-health, query-analytics) |
| `tests/test_telemetry.py` | 25 tests |
| `tests/test_federation.py` | 18 tests |
| `tests/test_self_tuning.py` | 8 tests |
| `tests/test_dashboard.py` | 4 tests |

### New CLI Commands

| Command | Purpose |
|---|---|
| `ingest-telemetry <traces.json> --kb .kb` | Map OpenTelemetry spans to graph nodes |
| `update-runtime-metadata --kb .kb` | Aggregate call counts, latency, error rates |
| `train-ranking-model --kb .kb --min-samples 20` | Train retrieval tuning config from feedback |
| `auto-tune --kb .kb` | Apply saved tuning overrides |
| `show-tuning-stats --kb .kb` | Show feedback count, useful rate, active overrides |
| `add-repo /path/to/other/.kb --name other --kb .kb` | Register another repository graph |
| `resolve-cross-repo --kb .kb` | Persist cross-repo references |
| `update-shared-deps --kb .kb` | Refresh shared dependency references |
| `dashboard --kb .kb` | Show graph health + retrieval analytics |
| `graph-health --kb .kb` | Show graph-only health metrics |
| `query-analytics --kb .kb` | Show retrieval feedback analytics |

---

## Phase 5: MCP Server + Interactive Dashboard + Pipeline Fixes — Đã hoàn thành

MCP server cho AI coding agents, interactive web dashboard, incremental enrichment, và LLM resilience fixes.

### Hạng mục bàn giao

| Thành phần | Status |
|---|---|
| MCP Server (stdio transport, 9 tools) | Done |
| Auto-init KB khi MCP server start | Done |
| File watcher (watchdog, auto-sync) | Done |
| Interactive web dashboard (FastAPI + D3.js) | Done |
| REST API endpoints (10 endpoints) | Done |
| Incremental enrichment command (`enrich`) | Done |
| LLM rate limiting (exponential backoff, chunked batch) | Done |
| LLM JSON format fallback | Done |
| Error resilience (failure logging, transient/permanent classification) | Done |
| Progress reporting (callback-based) | Done |
| `--skip-mem-ai` flag cho analyze | Done |

Test count lúc completion: 320

### File Manifest

**New Files**

| File | Purpose |
|---|---|
| `kb_agent/mcp_server/__init__.py` | MCP server module |
| `kb_agent/mcp_server/__main__.py` | Standalone entry point |
| `kb_agent/mcp_server/server.py` | MCP server setup, stdio transport, tool registration |
| `kb_agent/mcp_server/tools.py` | 9 KB tool implementations |
| `kb_agent/mcp_server/watcher.py` | File watcher for auto-sync (watchdog) |
| `kb_agent/mcp_server/auto_init.py` | Auto-detect and initialize KB |
| `kb_agent/dashboard/__init__.py` | Dashboard module |
| `kb_agent/dashboard/server.py` | FastAPI app, REST API endpoints |
| `kb_agent/dashboard/static/index.html` | Single-page dashboard (D3.js) |
| `kb_agent/analyzer/enricher.py` | Incremental KB enrichment |

**Modified Files**

| File | Changes |
|---|---|
| `kb_agent/analyzer/llm.py` | Rate limiting, JSON fallback, failure logging, bounded concurrency |
| `kb_agent/analyzer/pipeline.py` | Progress callback, `skip_mem_ai` parameter |
| `scripts/cli.py` | New commands: `serve`, `enrich`, web `dashboard`; new flags: `--skip-mem-ai`, `--watch`, `--retry-failed`, `--batch-size`, `--port`, `--no-browser` |

### New CLI Commands

| Command | Purpose |
|---|---|
| `serve --kb .kb [--watch]` | Start MCP server for AI coding agents |
| `enrich --kb .kb [--retry-failed] [--batch-size 5]` | Incremental LLM enrichment |
| `dashboard --kb .kb [--port 8080] [--no-browser]` | Launch interactive web dashboard |

### MCP Tools (9)

| Tool | Mô tả |
|---|---|
| `kb_search` | Tìm symbols theo tên/nghĩa (semantic search) |
| `kb_context` | Full retrieval + graph expansion |
| `kb_callers` | Tìm ai gọi function này |
| `kb_callees` | Tìm function này gọi ai |
| `kb_impact` | Phân tích ảnh hưởng khi thay đổi symbol |
| `kb_node` | Chi tiết một symbol |
| `kb_explore` | Source code của related symbols |
| `kb_status` | Trạng thái index |
| `kb_files` | Cấu trúc files đã index |

### Dashboard REST API (10 endpoints)

| Endpoint | Returns |
|---|---|
| `/api/status` | Graph health + manifest |
| `/api/nodes` | Nodes với filters |
| `/api/edges` | Edges với filters |
| `/api/search` | Semantic search |
| `/api/node/{id}` | Node detail + connections |
| `/api/hotpath` | Hot-path scores |
| `/api/features` | Feature clusters |
| `/api/file/{path}` | Source code (line-numbered) |
| `/api/stats` | Layer counts, language distribution |
| `/api/versions` | Temporal version list |

---

## Enum Registry

### EdgeKind (7 values)

`IMPORTS`, `CALLS`, `INHERITS`, `IMPLEMENTS`, `CONTAINS`, `USES_TYPE`, `BRIDGES_TO`

### QueryIntent (7 values)

`SYMBOL_LOOKUP`, `FLOW_TRACE`, `MODULE_OVERVIEW`, `RELATIONSHIP`, `CHAIN_TRACE`, `VERSION_DIFF`, `DEFAULT`

---

## Thống Kê Test

```text
320 tests total, breakdown theo file:
  test_scanner.py
  test_parser.py
  test_analyzer.py
  test_graph_builder.py
  test_graph_storage.py
  test_views.py
  test_retrieval.py
  test_query.py
  test_retrieval_benchmarks.py
  test_cli.py
  test_validator.py
  test_indexer.py
  test_confidence.py
  test_enhanced_resolution.py
  test_features.py
  test_planner.py
  test_hotpath.py
  test_graph_embedding.py
  test_temporal.py
  test_chain.py
  test_bridge.py
  test_telemetry.py
  test_federation.py
  test_self_tuning.py
  test_dashboard.py
  test_dashboard_server.py
  test_llm.py
```

Test count có thể thay đổi theo từng commit. Xem số gần nhất bằng `pytest -q`.
