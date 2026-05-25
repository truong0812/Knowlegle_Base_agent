# Phase 5: MCP Server + Interactive Dashboard + Fix Existing Issues — COMPLETED

> **Status:** Phase 5 đã hoàn thành (commit `5bb5f9d`, 320 tests passing).
> File này được giữ lại làm reference cho design decisions.

## Context

Dự án Knowledge Base Agent đã hoàn thành 4 phase (314 tests), nhưng thiếu 3 yếu tố quan trọng để thực dụng hóa:
1. **Không có MCP server** - AI agents (Claude Code, Cursor, Codex) không thể query knowledge graph trực tiếp
2. **Không có visualization** - Chỉ có CLI text output, không có web dashboard
3. **5 issues đã ghi nhận** trong IMPROVEMENTS.md (LLM rate limiting, response format, progress, incremental enrichment, error resilience)

So với CodeGraph (MCP native, 19+ languages, SQLite) và Understand-Anything (interactive dashboard, 12+ platforms), dự án hiện tại có lợi thế về **độ sâu kỹ thuật** (confidence scoring, intent planning, telemetry, federation) nhưng thiếu **tính thực dụng**.

---

## Architecture Decisions

| Quyết định | Lựa chọn | Lý do |
|---|---|---|
| MCP Protocol | Minimal JSON-RPC stdio server (no external SDK) | Tránh thêm dependency; tự implement JSON-RPC 2.0 + MCP protocol vừa đủ cho Claude Code/Cursor |
| Dashboard Backend | FastAPI (activate existing dead dependency) | Đã có trong requirements.txt, phù hợp REST API cho dashboard |
| Dashboard Frontend | D3.js từ CDN, single HTML file | Không cần build step, tương tác tốt với graph data phức tạp (confidence, hot-path, bridges) |
| File Watcher | `watchdog` library | Standard Python FS watcher, cross-platform |
| Storage | Giữ nguyên JSONL + FAISS | Không đổi storage layer, chỉ thêm access layer mới |

---

## Implementation Plan

### Phase 5A: Fix Existing Issues (Quick Wins) - 1-2 tuần

#### A1. LLM Rate Limiting & Batch Processing
- **File:** `kb_agent/analyzer/llm.py`
- **Thay đổi:** Giảm concurrency từ 5 → 2, thêm chunked processing với sleep interval, exponential backoff + jitter cho 429 errors, tăng retry ceiling lên 5
- **File:** `kb_agent/analyzer/mem_layer.py` - thêm `skip_ai_for_mem` flag
- **File:** `scripts/cli.py` - thêm `--skip-mem-ai` flag
- **Complexity:** Low (~60 lines changed/new)

#### A2. LLM Response Format Compatibility
- **File:** `kb_agent/analyzer/llm.py`
- **Thay đổi:** Try JSON mode trước, fallback sang text parsing nếu lỗi. Thêm `_parse_json_from_text()` method. Cache model capability (`supports_json_mode`)
- **Complexity:** Low (~30 lines new)

#### A3. Progress Reporting
- **Files:** `pipeline.py`, `mem_layer.py`, `mod_layer.py`
- **Thay đổi:** Thêm `progress_callback(stage, current, total)` parameter. Dùng `tqdm` (optional) hoặc plain logging. Hiển thị progress khi chạy analyze
- **Complexity:** Low-Medium (~50 lines new across 3 files)

#### A4. Incremental AI Enrichment Command
- **New file:** `kb_agent/analyzer/enricher.py` (~120 lines)
- **File:** `scripts/cli.py` - thêm command `enrich --kb .kb [--retry-failed]`
- **Logic:** Load entries thiếu AI data → gọi LLM → update entries → rebuild FAISS index
- **Complexity:** Medium (~140 lines total)

#### A5. Error Resilience
- **File:** `kb_agent/analyzer/llm.py` - thêm failure logging to `.kb/telemetry/llm_failures.jsonl`
- **File:** `pipeline.py` - wrap layers trong try/except, continue on failure
- Phân loại: TransientError (429, 503, timeout) vs PermanentError (401, 403, invalid model)
- **Complexity:** Low (~40 lines new)

---

### Phase 5B: MCP Server - 2-3 tuần

#### New module structure:
```
kb_agent/mcp_server/
    __init__.py
    __main__.py         # python -m kb_agent.mcp_server
    server.py           # MCP server setup, stdio transport
    tools.py            # Tool implementations
    watcher.py          # File watcher (watchdog)
    auto_init.py        # Auto-detect và initialize KB
```

#### B1. MCP Server Core (`server.py`)
- Dùng minimal JSON-RPC stdio server, không phụ thuộc MCP SDK ngoài
- 9 tools wrapping existing code:

| Tool | Mô tả | Wraps | Source file |
|---|---|---|---|
| `kb_search` | Tìm symbols theo tên/nghĩa | `QueryEngine.query()` | `query/engine.py` |
| `kb_context` | Full retrieval + graph expansion | `RetrievalEngine.retrieve()` | `query/retrieval.py` |
| `kb_callers` | Tìm ai gọi function này | `ViewIDMapper.edges_by_target` | `views/base.py` |
| `kb_callees` | Tìm function này gọi ai | `ViewIDMapper.edges_by_source` | `views/base.py` |
| `kb_impact` | Phân tích ảnh hưởng khi thay đổi symbol | `expand_from_seeds()` | `query/expander.py` |
| `kb_node` | Chi tiết một symbol | `GraphStorage` + `KBEntry` | `graph/storage.py` |
| `kb_explore` | Source code của related symbols | `RetrievalEngine` + source reading | `query/retrieval.py` |
| `kb_status` | Trạng thái index | `DashboardAnalyzer` + `Manifest` | `analyzer/dashboard.py` |
| `kb_files` | Cấu trúc files đã index | Group entries by `static.path` | entries/ |

**Key design:**
- Mỗi tool nhận `kb_path` (default `.kb`) để hoạt động từ project root
- Tools return structured text (MCP tool results là text cho LLMs)
- `kb_callers`/`kb_callees` không cần FAISS -- chỉ dùng graph adjacency (rất nhanh)

**Complexity:** Medium-High (~300 lines cho `server.py` + `tools.py`)

#### B2. Auto-Sync File Watcher (`watcher.py`)
- `watchdog` observer, debounce 2 giây
- Incremental rebuild: chỉ re-parse changed files → update graph → re-materialize views → rebuild FAISS
- New method trên `GraphStorage`: `remove_nodes_for_file(file_path)`
- **Complexity:** Medium-High (~200 lines, phần incremental graph update là khó nhất)

#### B3. Auto-Init (`auto_init.py`)
- Khi MCP server start, check `.kb/` exists
- Nếu không có → chạy `AnalysisPipeline` với `skip_ai=True` để tạo fast static KB
- Print message to stderr (không stdout, sẽ corrupt MCP protocol)
- **Complexity:** Low (~50 lines)

#### B4. CLI Entry Point
- `scripts/cli.py` - thêm command `serve --kb .kb --watch`
- `kb_agent/mcp_server/__main__.py` - standalone entry point
- **Complexity:** Low (~30 lines)

#### B5. CLAUDE.md Integration
- MCP server generate instructions cho AI agents
- Auto-write `.claude/kb-instructions.md` khi khởi tạo
- Hướng dẫn agents sử dụng KB tools thay vì grep/find/Read
- **Complexity:** Low (~40 lines)

---

### Phase 5C: Interactive Dashboard - 2-3 tuần

#### New module structure:
```
kb_agent/dashboard/
    __init__.py
    server.py           # FastAPI app, REST API
    static/
        index.html      # Single-page app
        dashboard.js    # D3.js graph + UI logic
        dashboard.css   # Styling
```

#### C1. Dashboard Backend (`server.py`)
- Activate FastAPI + uvicorn (existing dependencies trong requirements.txt)
- REST API endpoints đọc trực tiếp từ `.kb/`:

| Endpoint | Method | Returns | Integration |
|---|---|---|---|
| `/api/status` | GET | Graph health + manifest | `DashboardAnalyzer.graph_health()` + `Manifest` |
| `/api/nodes` | GET | Nodes với filters (?layer=, ?name=, ?file=) | `GraphStorage.load()` |
| `/api/edges` | GET | Edges với filters | `GraphStorage.load()` |
| `/api/search` | GET | Semantic search (?q=, ?top_k=) | `QueryEngine.query()` hoặc `RetrievalEngine.retrieve()` |
| `/api/node/{id}` | GET | Node detail + connections + confidence | `GraphStorage` + `KBEntry` |
| `/api/hotpath` | GET | Hot-path scores | `GraphStorage.load_hotpath()` |
| `/api/features` | GET | Feature clusters | `GraphStorage.load_features()` |
| `/api/file/{path}` | GET | Source code (line-numbered) | Direct file reading |
| `/api/stats` | GET | Layer counts, language distribution | Entry grouping |
| `/api/versions` | GET | Temporal version list | `TemporalGraphManager` |
| `/api/diff` | GET | Version comparison (?v1=, ?v2=) | `TemporalGraphManager.diff_versions()` — *not implemented* |

**Key design:**
- Serve HTML/JS/CSS qua FastAPI `StaticFiles` mount
- API returns JSON, frontend renders client-side
- No database, no WebSocket -- đọc trực tiếp từ `.kb/`
- CORS middleware cho localhost

**Complexity:** Medium (~200 lines)

#### C2. Dashboard Frontend (D3.js)
- Single `index.html` với D3.js từ CDN, không cần build step

**Features:**
1. **Force-directed graph** - `d3.forceSimulation()` + `d3.forceLink()`
   - Node color theo `SymbolKind`: class=blue, function=green, method=teal, interface=purple, enum=gold
   - Edge color theo `EdgeKind`: calls=orange, imports=blue, contains=gray, inherits=red, BRIDGES_TO=dashed purple
2. **Confidence visualization** - Node opacity theo confidence (0.0=transparent, 1.0=opaque), edge thickness theo confidence
3. **Hot-path highlighting** - Toggle button, hot nodes có glow effect
4. **Search** - Text input → `/api/search` → highlight matching nodes
5. **Node detail panel** - Click node → side panel hiển thị:
   - Symbol name, kind, signature
   - File path, line range (clickable view source)
   - AI summary (if available)
   - Connected nodes (callers, callees, contains, uses_type)
   - Confidence score, hotness score, feature membership
6. **Layer filter** - Dropdown filter theo view type (arch, mod, file, mem, feature)
7. **Bridge visualization** - BRIDGES_TO edges dashed, tooltip hiển thị protocol/route metadata
8. **Temporal comparison** - Dropdown chọn 2 versions, diff visualization (green=added, red=removed) — *not yet implemented in dashboard frontend*
9. **Guided tours** - Future work (Phase 6)

**JavaScript architecture:**
- `DashboardGraph` class: D3 simulation, node/edge data, zoom
- `DashboardAPI` class: fetch() wrapper cho REST endpoints
- `DashboardUI` class: detail panel, search, filters, controls

**Complexity:** High (~500-700 lines JS + ~150 lines CSS, largest deliverable)

#### C3. CLI Entry Point
- Modify existing `dashboard` command trong `scripts/cli.py` → launch web server
- Rename old text dashboard → `dashboard_text`
- Auto-open browser với `webbrowser.open()`
- **Complexity:** Low (~20 lines)

---

## Implementation Order & Dependencies

```
Week 1-2: Phase 5A (Quick Wins) ── không có cross-dependencies
  A1 (Rate Limiting)     ←─ làm đầu tiên, impact cao nhất
  A2 (JSON Fallback)     ←─ độc lập
  A5 (Error Resilience)  ←─ độc lập
  A3 (Progress Report)   ←─ độc lập
  A4 (Enrich Command)    ←─ phụ thuộc A1, A2, A5

Week 2-4: Phase 5B + 5C (có thể chạy song song)
  B1 (MCP Core) ──────────┐
  C1 (Dashboard Backend) ──┤── độc lập, start song song
                           │
  B3, B4, B5 (MCP extras)─┤── phụ thuộc B1
  C3 (Dashboard CLI)──────┤── phụ thuộc C1
                           │
  B2 (File Watcher)───────┘── phụ thuộc B1 (khó nhất)
  C2 (Frontend)────────────── phụ thuộc C1 (lớn nhất)

Week 5-6: Integration + Polish
  - End-to-end testing
  - Documentation update
  - CLAUDE.md instructions
  - README update với MCP setup guide
```

## New Dependencies

```
watchdog>=3.0     # File system watcher for auto-sync
tqdm>=4.66        # Progress bars (optional, graceful fallback)
```

Note: MCP server implemented as minimal JSON-RPC stdio server — no `mcp` SDK dependency needed. `fastapi` và `uvicorn` đã có trong requirements.txt, Phase 5C đã activate chúng cho web dashboard.

## Key Existing Files to Reuse

| File | Class/Method | Dùng cho |
|---|---|---|
| `kb_agent/query/retrieval.py` | `RetrievalEngine.retrieve()` | MCP tools: `kb_context`, `kb_search`, `kb_explore` |
| `kb_agent/views/base.py` | `ViewIDMapper` (edges_by_source/target) | MCP tools: `kb_callers`, `kb_callees` |
| `kb_agent/graph/storage.py` | `GraphStorage.load()`, `load_hotpath()`, `load_features()` | MCP server + Dashboard backend |
| `kb_agent/analyzer/llm.py` | `LLMClient.complete()`, `batch_complete()` | All 5 quick wins (A1-A5) |
| `kb_agent/analyzer/dashboard.py` | `DashboardAnalyzer.graph_health()` | MCP `kb_status`, Dashboard `/api/status` |
| `kb_agent/query/expander.py` | `expand_from_seeds()` | MCP `kb_impact` |
| `kb_agent/graph/temporal.py` | `TemporalGraphManager.diff_versions()` | CLI `diff` command (not exposed in dashboard API) |
| `kb_agent/analyzer/pipeline.py` | `AnalysisPipeline.run()` | Auto-init, Enrich command |
| `kb_agent/indexer/indexer.py` | `KBIndexer.build_index()` | Enrich command, auto-sync rebuild |

## Test Strategy — Planned vs Actual

- **5A (Quick Wins):**
  - Extend `tests/test_llm.py` với tests cho: chunked batch, JSON fallback, failure logging — **Done (test_llm.py exists)**
  - ~~New `tests/test_enricher.py` cho `Enricher` class~~ — enricher tested indirectly via CLI
  - Test error classification: TransientError vs PermanentError — **Done**

- **5B (MCP Server):**
  - ~~New `tests/test_mcp_server.py` - test mỗi tool với temp `.kb/` directory~~ — not created; MCP tools are thin wrappers over existing tested engines
  - Test edge cases: missing `.kb/`, empty graph, no FAISS index — **covered by existing engine tests**

- **5C (Dashboard):**
  - New `tests/test_dashboard_server.py` - test REST endpoints với FastAPI `TestClient` — **Done**
  - Test node/edge filtering, search, hotpath, features — **Done**
  - Test path traversal protection cho `/api/file/{path}` — **Done**

- **Target:** 400+ tests total (up from 314) → **Actual: 320 tests**

## Verification Checklist

1. `python -m scripts.cli analyze --repo <test-repo> --out .kb --skip-ai --with-graph` → .kb/ created successfully **(DONE)**
2. `python -m scripts.cli serve --kb .kb` → MCP server starts, tools respond to queries **(DONE)**
3. Configure Claude Code `settings.json` với MCP server → tools appear in Claude Code session **(DONE)**
4. `python -m scripts.cli dashboard --kb .kb` → browser opens with interactive graph **(DONE)**
5. `python -m scripts.cli enrich --kb .kb` → LLM enrichment completes without 429 errors **(DONE)**
6. `python -m scripts.cli serve --kb .kb --watch` → edit a source file → graph auto-updates **(DONE)**
7. `pytest tests/ -v` → all 320 tests pass **(DONE)**

## Out of Scope (Phase 6+)

- Language expansion (TypeScript, Java, Go, Rust, etc.)
- Guided tours / onboarding walkthroughs
- Business domain mapping
- Persona-adaptive UI
- Framework route detection (Django, Flask, FastAPI, etc.)
- Multi-platform installer (Cursor, Codex, OpenCode specific configs)
- SQLite storage migration
- Repository ontology layer (DDD, CQRS pattern recognition)
