# Knowledge Base Agent: MVP & Roadmap

> **Core principle:** Symbol Graph = source of truth. KB = cache/view layer.
> **Optimization target:** Retrieval precision, not document prettiness.
> **ID system:** Stable path-based IDs for overloads, partial classes, rename safety, cross-language consistency.

---

## Status Dashboard (Updated: 2026-05-14)

### Phase 1 (MVP) Progress

| Step | Description | Status | Branch | Details |
|------|-------------|--------|--------|---------|
| **Step 1** | Data models (SymbolNode, SymbolEdge, EdgeKind) | **DONE** | `feat/symbol-graph-builder` | `kb_agent/models/graph.py` + `kb_agent/parser/base.py` (CallInfo, TypeUsageInfo, bases) |
| **Step 2** | Parser enhancements (calls, type usage, bases) | **DONE** | `feat/symbol-graph-builder` | All 3 parsers: Python, C#, C++ — 9 resolution methods |
| **Step 3** | Graph builder + storage | **DONE** | `feat/symbol-graph-builder` | `builder.py` (7-phase build + 4 optimization indexes), `storage.py` (JSONL + adjacency) |
| **Step 4** | Materialized views (ARCH/MOD/FILE/MEM from graph) | **DONE** | `feat/symbol-graph-builder` | `kb_agent/views/` — 4 view builders with configurable depth + import weighting |
| **Step 5** | Retrieval engine (semantic + graph expansion) | **DONE** | `feat/retrieval-engine` | `kb_agent/query/retrieval.py`, `expander.py`, `composer.py`, `intent.py`, `mapper.py` |
| **Step 6** | Pipeline integration | **DONE** | `feat/symbol-graph-builder` | `--with-graph` + `--depth` flags in CLI, pipeline branches views vs old layers |
| **Step 7** | Tests + validation | **DONE** | `feat/symbol-graph-builder` | 20 view tests + 14 graph builder tests + 3 storage tests — 95/95 all pass |

### Phase 1 Summary

**Completed:** Steps 1, 2, 3, 4, 5, 6, 7 — **MVP Phase 1 fully complete**

- `--with-graph`: graph builder → 4 materialized views (ARCH/MOD/FILE/MEM)
- Without flag: old layer-based approach unchanged (zero breaking changes)
- 122/122 tests pass (95 graph + 27 retrieval)
- New `FILE` layer added to `Layer` enum
- `--depth N` option for configurable module grouping

**Completed:** Step 5 (Retrieval Engine)

- `RetrievalEngine` wraps `QueryEngine` for graph-aware retrieval
- Bounded BFS expansion: max 2 hops, 15 nodes, confidence >= 0.60
- Context composition: adaptive token budget (~4000 tokens), query-intent-driven
- Utility suppression + bidirectional traversal (incoming + outgoing edges)
- CLI: `query --with-graph` flag, backward-compatible fallback

### Phase 2–4 Status

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 2** | **TODO** | Confident Graph — enhanced resolution, confidence propagation, feature overlay, query planner |
| **Phase 3** | **TODO** | Intelligent Retrieval — cross-language bridging, temporal graph, hot-path learning, graph-aware embeddings |
| **Phase 4** | **TODO** | Production Intelligence — runtime telemetry, self-tuning retrieval, multi-repo graph, observability |

### Branch Map

| Branch | Purpose | Merged to main? |
|--------|---------|-----------------|
| `feat/mvp-implementation` | Initial MVP (scanner, parser, pipeline, validator) | No |
| `fix/code-quality-improvements` | Code quality fixes | No |
| `feat/symbol-graph-builder` | Symbol graph builder + parser enhancements | No |
| `docs/mvp-and-roadmap` | MVP documentation | No |

---

## 1. System Overview

### 1.1 Mục tiêu

Tạo 1 hệ thống chuyển codebase thành Knowledge Base (KB) để AI agent có thể:
- Query codebase mà không cần đọc source code trực tiếp
- Nhận context chính xác (high retrieval precision, low noise)
- Hiểu relationships giữa symbols (imports, calls, inheritance)

### 1.2 Kiến trúc tổng quan

```
                    ┌─────────────────────────┐
                    │     SYMBOL GRAPH         │
                    │     (source of truth)    │
                    │                          │
                    │  Nodes: symbols          │
                    │  Edges: relationships    │
                    │  IDs: stable path-based  │
                    └──────────┬───────────────┘
                               │
                     materialize thành views
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
          ┌──────────┐  ┌──────────┐  ┌──────────┐
          │ ARCH View │  │ MOD View │  │ FILE View │
          └──────────┘  └──────────┘  └──────────┘
                ▲              ▲              ▲
                │              │              │
                └──────────────┼──────────────┘
                      KB = cache/view layer
                optimize cho RETRIEVAL PRECISION
```

### 1.3 15 vấn đề đã identify

| # | Vấn đề | Mức độ ưu tiên |
|---|--------|----------------|
| 1 | Symbol Resolution chưa đủ mạnh | MVP-blocking |
| 2 | Feature detection fuzzy | MVP address (deterministic) |
| 3 | Import-aware grouping chưa đủ | MVP address (edge weighting) |
| 4 | Dynamic languages (monkey patching, decorators) | Defer Phase 2 |
| 5 | Graph traversal explosion | MVP-blocking |
| 6 | Confidence system chưa hoàn chỉnh | MVP address (basic) |
| 7 | Graph ontology chưa define | MVP address (minimal) |
| 8 | Materialized views stale cache | Engineering discipline |
| 9 | Query planner chưa có | MVP address (simple strategy) |
| 10 | Temporal graph | Defer Phase 3 |
| 11 | Cross-language semantic bridging | Defer Phase 3 |
| 12 | Hot-path learning từ runtime telemetry | Defer Phase 3 |
| 13 | Embedding strategy mơ hồ | MVP address (summary embed) |
| 14 | Context composition (hardest problem) | MVP address (heuristic) |
| 15 | Complexity tăng quá nhanh | Aggressive scoping |

---

## 2. MVP (Phase 1)

### 2.1 Scope

**MVP = Symbol Graph + Materialized Views + Basic Retrieval**

Mục tiêu: Agent có thể query "What does function X do?" và nhận context chính xác với relationships.

### 2.2 Symbol Graph

#### Node

```python
class SymbolNode:
    id: str           # Stable path-based ID
    kind: SymbolKind  # class, function, method, interface, etc.
    language: Language
    path: str         # File path relative to repo root
    line_start: int
    line_end: int
    signature: str | None
    modifiers: list[str]
    parameters: list[Parameter]
    return_type: str | None
    docstring: str | None
```

#### ID Format

```
repo/{relative_path}::{ScopeName.}SymbolName({param_types})
```

Ví dụ:

| Symbol | ID |
|--------|-----|
| Top-level function `login` trong `auth.py` | `repo/src/auth.py::login(email, password)` |
| Method `validate_token` trong class `AuthMiddleware` | `repo/src/middleware/auth.py::AuthMiddleware.validate_token(token: str)` |
| Overloaded method `process` (2 overloads) | `repo/src/handler.py::Handler.process(data: dict)` và `repo/src/handler.py::Handler.process(data: str, format: str)` |
| C# partial class `UserService` | `repo/Services/UserService.cs::UserService` và `repo/Services/UserService.Helpers.cs::UserService` |
| C++ class `Parser` | `repo/include/parser.hpp::Parser` |

**Tại sao path-based ID:**

| Vấn đề | Giải pháp |
|---------|-----------|
| Overloads (cùng tên, khác params) | Signature included trong ID |
| Partial classes (C#, cùng tên class ở nhiều file) | File path khác nhau → ID khác nhau |
| Rename symbol | Path stable → chỉ cần re-resolve symbol name |
| Cross-language | Extension trong path → language rõ ràng |
| Dedup | Line number fallback nếu signature trùng |

#### Edge

```python
class SymbolEdge:
    source: str        # Node ID
    target: str        # Node ID
    kind: EdgeKind     # imports, calls, inherits, implements, uses_type
    confidence: float  # 0.0 - 1.0
    source_type: str   # "deterministic", "heuristic", "inferred"
    resolution: str    # HOW edge was resolved — determines confidence
```

`resolution` field là khóa để graduate confidence. Thay vì gán 1 giá trị flat cho mỗi edge kind, confidence được xác định bởi **cách resolve** dẫn đến edge đó.

#### Graph Ontology (MVP — minimal)

| Edge Kind | Semantics | Example | Default Confidence |
|-----------|-----------|---------|-------------------|
| `imports` | File A imports symbol từ file B | `from auth import login` | 0.95 |
| `inherits` | Class A kế thừa class B | `class Admin(User)` | 0.95 |
| `implements` | Class A implement interface B | `class AuthValidator(IValidator)` | 0.90 |
| `contains` | Class A chứa method B | `AuthMiddleware.validate_token` | 1.00 |
| `calls` | Function A gọi function B | `login()` calls `verify()` | Graduated (see below) |
| `uses_type` | Function A dùng type B trong params/return | `def get_user(id: int) -> User` | 0.80 |

#### Graduated `calls` Confidence

`calls` là edge kind khó resolve nhất. Confidence được assign theo resolution method, KHÔNG dùng giá trị flat:

| Resolution Method | Mô tả | Confidence | Add to graph? |
|---|---|---|---|
| `same_scope` | `self.method()` hoặc method trong cùng class | 0.85 | Yes |
| `same_file` | Gọi function trong cùng file, không qua alias | 0.80 | Yes |
| `direct_import` | `from x import func` → gọi `func()` | 0.75 | Yes |
| `constructor` | `ClassName()` → constructor call | 0.75 | Yes |
| `static_call` | `ClassName.method()` → static/class method | 0.80 | Yes |
| `aliased_import` | `from x import func as f` → gọi `f()` | 0.45 | No (< 0.50) |
| `dynamic_dispatch` | `obj.method()` — type của `obj` không biết | 0.35 | No (< 0.50) |
| `callback` | Callback/event handler — target không xác định | 0.30 | No (< 0.50) |
| `unresolved` | Không tìm thấy target | 0.00 | No |

**Rule: Resolution method có confidence < 0.50 → KHÔNG thêm edge vào graph.**

#### Confidence-aware Edge Resolution

```
┌──────────────────────────────────────────────────────────┐
│  EDGE RESOLUTION STRATEGY                                │
│                                                          │
│  1. DETERMINISTIC (confidence: 0.90-1.00)               │
│     - Tree-sitter/AST extract trực tiếp                  │
│     - imports, inherits, implements, contains            │
│     - Không ambiguity                                    │
│                                                          │
│  2. HEURISTIC (confidence: 0.50-0.89)                   │
│     - calls: confidence graduated theo resolution method │
│     - uses_type: từ type annotations                     │
│     - Có thể sai nếu alias/overload                      │
│                                                          │
│  3. INFERRED (confidence: 0.00-0.49)                    │
│     - calls qua LLM analysis                            │
│     - cross-file relationships không resolve được        │
│     - Chỉ dùng khi không có deterministic/heuristic      │
│                                                          │
│  RULE: Thà thiếu edge còn hơn edge sai.                  │
│  Edge có confidence < 0.50: KHÔNG thêm vào graph.        │
└──────────────────────────────────────────────────────────┘
```

**Cách resolve `calls` trong MVP:**

```
Input: auth.py gọi login(email, password)

Step 1: Check resolution context
  → Gọi qua self/this? → resolution: "same_scope", confidence: 0.85
  → Gọi constructor (ClassName())? → resolution: "constructor", confidence: 0.75
  → Gọi static method (ClassName.method())? → resolution: "static_call", confidence: 0.80

Step 2: Check imports trong file
  → from services.auth_service import login ✅
  → Không qua alias? → resolution: "direct_import", confidence: 0.75
  → Via alias (import login as x)? → resolution: "aliased_import", confidence: 0.45 → SKIP

Step 3: Check symbols trong cùng file
  → Tìm thấy? → resolution: "same_file", confidence: 0.80

Step 4: Nếu không tìm thấy target
  → resolution: "unresolved", confidence: 0.00 → Skip edge. KHÔNG guess.
```

### 2.3 Materialized Views

Views là pre-computed query patterns trên graph. Mỗi view trả lời 1 loại câu hỏi.

#### ARCH View (1 entry)

**Câu hỏi:** "Dự án này làm gì?"

```
Materialize từ graph:
  - Count nodes theo language
  - Extract top-level paths
  - Detect entry points (main(), Program.cs, __init__.py)
  - Count edges by kind
  → 1 ARCH entry với summary
```

#### MOD View (N entries)

**Câu hỏi:** "Module X chứa gì? Public API?"

```
Materialize từ graph:
  - Group nodes theo configurable depth (thay vì hardcoded parts[0])
  - Weight imports: business imports = high, utility imports = low
  - Suppress utility edges trước khi cluster
  → N MOD entries
```

**Configurable depth:**
```
depth=1: src/                    → module "src"
depth=2: src/services/           → module "src/services"
depth=3: src/services/auth/      → module "src/services/auth"
```

**Import weighting (giải quyết vấn đề #3):**
```
Edge weight rules:
  - business logic imports  → weight 1.0 (auth, user, payment)
  - standard library imports → weight 0.0 (os, sys, logging)
  - utility imports         → weight 0.1 (helpers, utils, config)
  - test imports            → weight 0.0

Clustering chỉ dùng edges có weight >= 0.5
→ Tránh "giant connected component" từ utility files
```

#### FILE View (F entries) — MỚI

**Câu hỏi:** "File X chứa gì? Symbols liên quan nhau thế nào?"

```
Materialize từ graph:
  - Extract tất cả nodes trong 1 file
  - Extract intra-file edges (contains, calls giữa symbols trong file)
  → F FILE entries
```

Output cho mỗi FILE entry:
```
ID: repo/src/middleware/auth.py
Nodes:
  - AuthMiddleware (class)
    ├── validate_token(token: str) → bool
    └── refresh_token(token: str) → str
  - create_session(user_id: int) → Session
  - revoke_session(session_id: str) → void

Intra-file edges:
  validate_token ──calls──→ create_session (confidence: 0.70)
  revoke_session ──calls──→ SessionStore.delete (confidence: 0.60)

External edges:
  AuthMiddleware ──imports──→ repo/src/models/user.py::User
  AuthMiddleware ──imports──→ repo/src/services/auth_service.py::AuthService
```

#### MEM View (M entries)

**Câu hỏi:** "Symbol X làm gì cụ thể?"

```
Materialize từ graph:
  - 1 node + outgoing edges
  - FILE context (summary của file chứa symbol)
  - MOD context (summary của module)
  → M MEM entries
```

### 2.4 Retrieval (Basic)

MVP retrieval strategy — giải quyết vấn đề #5 (traversal explosion) và #14 (context composition cơ bản):

```
┌──────────────────────────────────────────────────────────┐
│  RETRIEVAL PIPELINE (MVP)                                │
│                                                          │
│  Step 1: SEMANTIC SEARCH                                 │
│    Query → embed → FAISS search → top_k candidate nodes  │
│                                                          │
│  Step 2: GRAPH EXPANSION (bounded)                       │
│    Từ candidate nodes, expand qua edges:                 │
│    - Max hops: 2                                         │
│    - Max nodes: 15                                       │
│    - Edge filter: confidence >= 0.60                     │
│    - Suppress utility nodes (logging, metrics, config)   │
│                                                          │
│  Step 3: CONTEXT COMPOSITION                             │
│    Assemble context từ expanded subgraph:                │
│    - Entry nodes (từ semantic search): full detail       │
│    - 1-hop neighbors: summary only                       │
│    - 2-hop neighbors: name + type only                   │
│    - Total context budget: ~4000 tokens                  │
│                                                          │
│  Step 4: RETURN                                          │
│    Structured context cho AI agent                       │
└──────────────────────────────────────────────────────────┘
```

**Traversal budget (giải quyết #5):**

```
Budget constraints:
  - Max hops from entry point: 2
  - Max total nodes: 15
  - Max edges per node: 5
  - Utility suppression: nodes tagged "logging|metrics|config|serialization" → skip
  - Confidence threshold: edges < 0.60 → skip
```

**Context composition (giải quyết #14 ở mức cơ bản):**

```
Token budget: ~4000 tokens per query response
```

Fixed ratio (40/35/15/10) là điểm bắt đầu, KHÔNG phải giá trị cuối. Thay vào đó, dùng adaptive budget:

```
Adaptive Budget Strategy:

1. Base budget: 4000 tokens

2. Query intent factor — ratio thay đổi theo loại query:
   - SYMBOL_LOOKUP → entry: 60%, 1-hop: 20%, 2-hop: 10%, meta: 10%
   - FLOW_TRACE    → entry: 25%, 1-hop: 45%, 2-hop: 20%, meta: 10%
   - RELATIONSHIP  → entry: 30%, 1-hop: 40%, 2-hop: 20%, meta: 10%
   - Default       → entry: 40%, 1-hop: 35%, 2-hop: 15%, meta: 10%

3. Per-node cap: max 500 tokens/node
   → Tránh 1 node phức tạp (class 20 methods) chiếm hết budget
   → Nếu node exceed cap → truncate to signature + summary only

4. Truncation priority (khi exceed budget):
   → 2-hop neighbors bị truncate trước (giữ name + kind only)
   → 1-hop neighbors bị truncate tiếp (gi giữ summary)
   → Entry node bị truncate cuối (luôn giữ signature)

5. Hard limits:
   → Max 15 nodes total in response
   → Max 5 edges per node shown
   → Utility nodes suppressed regardless of budget
```

**Instrumentation để measure và tune:**

```python
class RetrievalMetrics:
    query: str
    intent: str                    # SYMBOL_LOOKUP, FLOW_TRACE, etc.
    seed_nodes: list[str]          # Entry nodes từ semantic search
    expanded_nodes: list[str]      # Nodes sau graph expansion
    token_allocation: dict[str, int]  # {entry: 1600, hop1: 1400, hop2: 600, meta: 400}
    truncated: bool                # Có exceed budget không?
    truncated_nodes: list[str]     # Nodes bị bỏ vì budget
    total_tokens_used: int
```

Log `RetrievalMetrics` mỗi query → có data thật để tune ratio trong Phase 2.
Không tune bằng guessing. Tune bằng measurement.

### 2.5 Embedding Strategy (MVP — giải quyết #13)

```
Embedding target: AI summary text của mỗi node
  - Nếu có ai.summary → embed summary
  - Nếu không → embed signature
  - Nếu không có signature → embed "{kind} {name}"

Chunk level: per-symbol (1 embedding per node)
  - Không embed file-level (quá coarse)
  - Không embed source code (quá noisy)

Index: FAISS L2 (giống hiện tại)
```

### 2.6 Confidence System (MVP — giải quyết #6 ở mức basic)

```
Node confidence:
  - deterministic data (parser output): confidence = 1.0
  - LLM-generated summary: confidence = LLM-assigned (0.0-1.0)

Edge confidence:
  - deterministic edges (imports, inherits, contains): 0.90-1.00
  - heuristic edges (calls, uses_type): 0.50-0.89
  - inferred edges (LLM): 0.00-0.49 → KHÔNG thêm vào graph

Propagation (MVP: không implement)
  - Deferred to Phase 2
```

### 2.7 Incremental Updates (giải quyết #8)

```
Strategy: hash-based invalidation + orphan cleanup
```

#### Hash-based Invalidation

```
1. Store file content hash trong manifest
2. On re-run:
   - Diff file hashes → identify changed/added/removed files
   - Re-parse only changed + added files
   - Re-compute nodes/edges for changed files
```

#### Orphan Cleanup Pipeline

Khi file bị xóa hoặc symbol bị đổi tên, nodes/edges cũ vẫn còn trong graph → cần cleanup:

```
Step 1: DIFF — So sánh old parse output vs new parse output
  → removed_nodes: nodes trong old nhưng không trong new
  → added_nodes: nodes trong new nhưng không trong old
  → modified_nodes: nodes trong cả hai nhưng signature thay đổi

Step 2: REMOVE — Xóa removed_nodes khỏi graph
  → Xóa tất cả edges có source hoặc target là removed_node
  → Log removed edges cho downstream invalidation

Step 3: CASCADE — Kiểm tra nodes bị ảnh hưởng
  → Nodes có edge trỏ đến removed_node → mark là "stale"
  → Modules chứa removed_node → mark module view là "stale"

Step 4: REBUILD — Re-materialize stale views
  → Re-materialize FILE view cho changed/stale files
  → Re-materialize MEM view cho symbols trong stale files
  → Re-materialize MOD view cho modules bị mark stale
  → Re-materialize ARCH view only if language counts changed

Step 5: VALIDATE — Orphan check
  → Verify không còn edge nào trỏ đến node không tồn tại
  → Verify không còn view nào reference node đã bị xóa
  → Report orphan count trong quality_report.json
```

#### Edge Cases

```
- File renamed: treated as remove old + add new → all edges updated
- Symbol renamed within file: treated as remove old node + add new node
- Import removed: edges từ importing file → mark stale, re-resolve
- File deleted: all nodes/edges removed, cascade to views
- Circular dependency: cleanup handles by removing all edges first, then rebuilding
```

### 2.8 MVP Explicitly EXCLUDES

| Feature | Lý do exclude |
|---------|---------------|
| Cross-language call resolution (#11) | Cần runtime data hoặc protocol analysis |
| Temporal graph / PR diff (#10) | Feature phức tạp, cần versioned graph |
| Runtime telemetry / hot paths (#12) | Cần integration với external systems |
| Graph-aware embeddings (#13 advanced) | Research problem |
| Advanced query planner (#9 advanced) | Cần data về query patterns trước |
| Dynamic language resolution (#4) | 80% use cases không cần |
| LLM-inferred edges | Thà thiếu còn hơn sai |
| Feature overlay (#2) | Cần stable graph trước khi thêm overlay |

### 2.9 MVP Pipeline

```
PHASE 1: BUILD GRAPH
  SCAN (quét files, detect languages)
    → detect_language() per file (giống hiện tại)
    → filter .kbignore (giống hiện tại)
    ↓
  PARSE (parallel per file)
    → Extract symbols (giống hiện tại, tree-sitter + AST)
    → Extract imports (giống hiện tại)
    → NEW: Extract calls (heuristic, name-matching within scope)
    → NEW: Extract type usage (from annotations/signatures)
    ↓
  BUILD GRAPH
    → Create SymbolNodes với stable path-based IDs
    → Create SymbolEdges với confidence scores
    → Store graph: adjacency list format

PHASE 2: MATERIALIZED VIEWS
  ARCH view ← aggregate graph metadata
    ↓
  MOD view ← group nodes (configurable depth + import weighting)
    ↓
  FILE view ← per-file subgraph extraction
    ↓
  MEM view ← per-symbol with file + module context

PHASE 3: INDEX + QUERY
  Build FAISS index (summary embeddings)
  Build graph index (adjacency lookup)
  Query engine: semantic search → graph expansion → context composition
```

### 2.10 Data Storage

```
.kb/
├── graph/
│   ├── nodes.jsonl          # Mỗi line = 1 SymbolNode
│   ├── edges.jsonl          # Mỗi line = 1 SymbolEdge
│   └── adjacency.json       # {node_id: [edge_ids]} cho fast lookup
├── views/
│   ├── arch/                # ARCH view entries
│   ├── mod/                 # MOD view entries
│   ├── file/                # FILE view entries (NEW)
│   └── mem/                 # MEM view entries
├── index/
│   ├── faiss.index          # Vector index
│   └── id_map.json          # FAISS ID → node ID mapping
├── manifest.json            # Metadata, file hashes (for incremental)
└── quality_report.json      # Validation results
```

### 2.11 MVP Success Criteria

| Metric | Target |
|--------|--------|
| Symbol extraction accuracy | >= 95% (same as current) |
| Edge resolution accuracy (imports, inherits) | >= 90% |
| Edge resolution accuracy (calls) | >= 60% (acceptable for MVP) |
| Retrieval relevance (top-5) | Manual evaluation: 4/5 relevant |
| Incremental update time | < 10% of full rebuild |
| Total LLM cost | Same order as current (1 + N + F + M calls) |

---

## 3. Phase 2: Confident Graph

**Goal:** Tăng accuracy của graph, thêm confidence propagation, feature overlay.

### 3.1 Enhanced Symbol Resolution (giải quyết #1 full, #4 partial)

```
Improvements:
  - Alias resolution: track import aliases → resolve correctly
    from auth import login as auth_login
    auth_login() → resolved to auth.login ✅

  - Scope-aware call resolution:
    class UserService:
        def create(self): ...
        def get(self): ...
    Within UserService.create(), self.get() → UserService.get ✅

  - Type inference (basic):
    def get_service() -> AuthService: ...
    svc = get_service()
    svc.login() → resolved to AuthService.login ✅ (via return type)

  - Decorator handling:
    @staticmethod, @classmethod → adjust scope resolution
    @inject → mark as dependency injection, confidence = 0.50

  NOT included:
    - Full type inference (too complex)
    - Dynamic dispatch resolution (need runtime data)
    - Reflection/generated code
```

### 3.2 Confidence Propagation (giải quyết #6 full)

```
Node confidence:
  - Base: 1.0 (deterministic) or LLM-assigned
  - Incoming edge bonus: if 3+ high-confidence edges → boost confidence
  - Decay: confidence decreases with distance from verified source

Edge confidence:
  - Base: from resolution strategy (deterministic/heuristic/inferred)
  - Decay: traversed edges lose confidence per hop
    hop 0: full confidence
    hop 1: confidence × 0.8
    hop 2: confidence × 0.6
    hop 3+: not traversed (cut off)

Propagated confidence:
  node_confidence = base_confidence × (1 + edge_bonus)
  edge_effective_confidence = base_confidence × decay_factor
```

### 3.3 Feature Overlay (giải quyết #2)

```
Feature detection strategy (deterministic, không dùng LLM clustering):

Step 1: Extract noun clusters from symbol names
  validate_token, create_session, revoke_session, login, logout
  → cluster: "token", "session", "auth"

Step 2: Group symbols sharing nouns
  symbols chứa "token" → feature "token_management"
  symbols chứa "session" → feature "session_management"
  symbols chứa "auth" → feature "authentication"

Step 3: Merge overlapping features
  token_management ∩ authentication → merge thành "authentication"
  (vì symbols overlap >= 50%)

Step 4: Name features by shared noun
  Không dùng LLM → deterministic naming
  "authentication", "user_management", "payment", etc.

Output:
  Feature entry = {
    id: "feature.authentication",
    member_nodes: [list of node IDs],
    naming_basis: "auth" (shared noun),
    edge_density: 12 (edges between members),
  }
```

### 3.4 Query Planner (Basic — giải quyết #9 partial)

```
Query types:
  1. SYMBOL_LOOKUP: "What does validate_token do?"
     → Semantic search → return node + 1-hop context

  2. FLOW_TRACE: "How does login work?"
     → Find entry point → expand via calls edges → build call chain
     → Budget: max 10 nodes, follow calls edges only

  3. MODULE_OVERVIEW: "What's in the auth module?"
     → Return MOD view + list of FILE views

  4. RELATIONSHIP: "What uses AuthService?"
     → Reverse graph traversal: find all nodes with edge → AuthService
     → Return list of callers/dependents

Intent detection:
  - Keywords: "how does", "flow", "process" → FLOW_TRACE
  - Keywords: "what does", "explain" → SYMBOL_LOOKUP
  - Keywords: "what's in", "overview" → MODULE_OVERVIEW
  - Keywords: "what uses", "depends on", "callers" → RELATIONSHIP
  - Default: SYMBOL_LOOKUP
```

### 3.5 Phase 2 Success Criteria

| Metric | Target |
|--------|--------|
| Call resolution accuracy | >= 75% (up from 60%) |
| Alias resolution | >= 85% |
| Feature overlay consistency | Same features on 3 consecutive runs |
| Query relevance (top-5) | 4.5/5 relevant |

---

## 4. Phase 3: Intelligent Retrieval

**Goal:** Cross-language flows, temporal awareness, advanced context composition.

### 4.1 Cross-Language Semantic Bridging (giải quyết #11)

```
Problem:
  Frontend TS → API call → Backend C# → Python ML service

Static analysis không resolve inter-language calls.

Strategy:
  - Detect API endpoints (decorators, route attributes, HTTP handlers)
  - Match by URL path:
    Frontend: fetch("/api/auth/login")
    Backend: [HttpPost("/api/auth/login")]
    → Bridge edge: confidence 0.70

  - Detect message queue / event patterns:
    Publisher: channel.publish("user.created", data)
    Subscriber: @subscribe("user.created")
    → Bridge edge: confidence 0.60

  - Detect shared data contracts:
    C# DTO: class LoginRequest { Email, Password }
    Python model: class LoginRequest: email: str, password: str
    → Bridge edge: confidence 0.50 (structural similarity)

Output:
  New edge kind: "bridges_to" (inter-language)
  Confidence: 0.50-0.70 (always heuristic)
```

### 4.2 Temporal Graph (giải quyết #10)

```
Structure:
  - Each node/edge has valid_from (commit sha, timestamp)
  - Optional valid_to (null = still current)
  - Graph snapshots at commit boundaries

Capabilities:
  - "What changed in auth module after PR #142?"
    → Diff graph snapshots: new/removed/modified nodes and edges
    → Return delta summary

  - "How did login flow evolve over last month?"
    → Traverse temporal graph at multiple snapshots
    → Return timeline of changes

Storage:
  .kb/
  └── temporal/
      ├── snapshots/
      │   ├── abc1234.jsonl    # Nodes at commit abc1234
      │   └── def5678.jsonl
      └── deltas/
          ├── abc1234..def5678.jsonl  # Diff between commits
          └── def5678..ghi9012.jsonl
```

### 4.3 Hot-Path Learning (giải quyết #12)

```
Data sources:
  - Runtime tracing (OpenTelemetry, Jaeger)
  - Access logs (request frequency)
  - Profiling data (CPU hot spots)

Integration:
  - Import trace data → identify frequently traversed paths
  - Weight edges: hot paths get higher traversal priority
  - Annotate nodes: "hot_path: true, avg_calls_per_min: 500"

Effect on retrieval:
  - Query "how does login work?" → prioritize hot path over cold path
  - Query "why is login slow?" → show hot path + timing data

MVP for hot paths (without runtime data):
  - Use static heuristics:
    * Entry points (main, controllers) → high weight
    * Symbols called by many others → high weight
    * Test coverage (symbols tested → likely important)
```

### 4.4 Graph-Aware Embeddings (giải quyết #13 advanced)

```
Current: embed summary text only (flat)
Improved: embed with graph context

Approach 1: Structure-aware text
  Embedding input = summary + " calls " + called_function_summaries
  → Embedding captures some structural info

Approach 2: Graph neural network
  - GNN over symbol graph → node embeddings
  - Captures neighborhood structure
  - Better for structural queries ("find similar patterns")

Approach 3: Hybrid
  - Text embedding (semantic similarity)
  - Graph embedding (structural similarity)
  - Combine scores at query time

Phase 3 implements Approach 1 (simplest, good enough).
Approach 2/3 deferred to research.
```

### 4.5 Advanced Context Composition (giải quyết #14 full)

```
Context ranking engine:
  - Relevance score = semantic_similarity × confidence × edge_weight
  - Causal chain detection: identify A→B→C chains from query
  - Utility suppression: config/logging/metrics → always lowest priority

Relevance propagation model:
  1. Start from semantic search results (seed nodes)
  2. Score each seed by semantic similarity
  3. Expand to neighbors, propagate scores:
     neighbor_score = seed_score × edge_confidence × decay
  4. Rank all nodes by score
  5. Select top N within token budget

Example:
  Query: "Why does login timeout sometimes happen?"

  Seed nodes (semantic search):
    auth_service.login (score: 0.92)
    timeout_handler (score: 0.85)

  Expansion:
    login → calls → User.authenticate (0.92 × 0.70 = 0.64)
    login → calls → Cache.get (0.92 × 0.70 = 0.64)
    login → calls → DB.query (0.92 × 0.65 = 0.60)
    timeout_handler → references → Config.timeout_ms (0.85 × 0.80 = 0.68)
    DB.query → uses → ConnectionPool (0.60 × 0.60 = 0.36) ← suppressed

  Final context (top 6 by score):
    auth_service.login, timeout_handler, Config.timeout_ms,
    User.authenticate, Cache.get, DB.query
```

### 4.6 Phase 3 Success Criteria

| Metric | Target |
|--------|--------|
| Cross-language edge accuracy | >= 60% for API-based bridging |
| Temporal query accuracy | Correct diff for >= 90% of tested PRs |
| Context composition relevance | 4.5/5 for causal queries |
| End-to-end retrieval latency | < 500ms for graph expansion |

---

## 5. Phase 4: Production Intelligence

**Goal:** Runtime integration, self-tuning, production-grade observability.

### 5.1 Runtime Telemetry Integration

```
- OpenTelemetry trace ingestion
- Map traces to symbol graph nodes
- Annotate graph with runtime data:
  * Call frequency
  * Latency percentiles
  * Error rates
  * Memory allocation
```

### 5.2 Self-Tuning Retrieval

```
- Log query → response → agent feedback (useful/not useful)
- Train retrieval ranking model on feedback data
- Auto-tune: edge weights, hop limits, suppression rules
- A/B test different retrieval strategies
```

### 5.3 Multi-Repository Graph

```
- Federated graph across multiple repos
- Cross-repo dependency tracking
- Shared library versioning
- Organization-wide knowledge base
```

### 5.4 Graph Observability

```
- Graph health dashboard
  * Edge density over time
  * Confidence distribution
  * Orphan node detection
  * Stale view detection

- Retrieval analytics
  * Query latency distribution
  * Retrieval relevance distribution
  * Popular query patterns
  * Low-retrieval-quality areas

- Debug tools
  * "Why was this node included in context?"
  * "Why was this node NOT included?"
  * Graph traversal visualizer
```

---

## 6. Implementation Priority Within Each Phase

### Phase 1 (MVP) — Ordered by dependency

| Step | Status | Description | Key Files |
|------|--------|-------------|-----------|
| Step 1 | **DONE** `745c0e9` | Data model: SymbolNode, SymbolEdge, EdgeKind, confidence metadata | `kb_agent/models/graph.py` (NEW), `kb_agent/parser/base.py` (CallInfo, TypeUsageInfo, bases) |
| Step 2 | **DONE** `745c0e9` | Parser enhancements: extract calls (9 resolution methods), type usage, base classes for all 3 languages | `kb_agent/parser/python_parser.py`, `csharp_parser.py`, `cpp_parser.py` |
| Step 3 | **DONE** `745c0e9` | Graph builder: 7-phase build, graduated confidence edges, 4 optimization indexes (O(1) lookups, O(log N) enclosing node), JSONL + adjacency storage | `kb_agent/graph/builder.py` (NEW), `kb_agent/graph/storage.py` (NEW) |
| Step 4 | **DONE** | Materialized views: 4 view builders (ARCH/MOD/FILE/MEM) derived from graph, configurable depth, import weighting, utility suppression | `kb_agent/views/base.py`, `arch_view.py`, `mod_view.py`, `file_view.py`, `mem_view.py` (NEW) |
| Step 5 | **DONE** | Retrieval engine: graph expansion (bounded BFS), context composition (adaptive token budget), intent classification, entry-to-node mapping | `kb_agent/query/retrieval.py`, `expander.py`, `composer.py`, `intent.py`, `mapper.py` (NEW) |
| Step 6 | **DONE** | Pipeline integration: `--with-graph` + `--depth` CLI flags, pipeline branches views vs old layers | `kb_agent/analyzer/pipeline.py`, `scripts/cli.py` |
| Step 7 | **DONE** | Tests: 20 view tests + 14 graph builder tests + 3 storage tests — 95/95 all pass | `tests/test_views.py` (NEW), `tests/test_graph_builder.py`, `tests/test_graph_storage.py` |

#### Completed Work Details (Steps 1-4, 6-7)

**Data Models (`kb_agent/models/graph.py`)**
- `EdgeKind` enum: IMPORTS, CALLS, INHERITS, IMPLEMENTS, CONTAINS, USES_TYPE
- `SymbolNode`: id, name, kind, language, path, line_start/end, signature, modifiers, parameters, return_type, docstring
- `SymbolEdge`: source, target, kind, confidence (0.0-1.0), source_type, resolution

**Parser Enhancements (all 3 languages)**
- `_extract_calls()`: walk AST for call nodes, resolve with 9 methods (same_scope, same_file, direct_import, constructor, static_call, aliased_import, dynamic_dispatch, callback, unresolved)
- `_extract_type_usages()`: extract type refs from parameters, return types, annotations
- Base class extraction: Python (`argument_list`), C# (`base_list`), C++ (`base_class_clause`)

**Graph Builder (`kb_agent/graph/builder.py`)**

7-phase build pipeline:
1. `_build_import_map()` — resolve imports to source files
2. `_create_nodes_from_symbols()` — stable path-based IDs with dedup
3. `_create_contains_edges()` — class → method (confidence 1.0)
4. `_create_imports_edges()` — file → imported symbols (confidence 0.95)
5. `_resolve_calls_edges()` — graduated confidence by resolution method
6. `_create_type_usage_edges()` — type annotations (confidence 0.80)
7. `_create_inheritance_edges()` — base classes (confidence 0.95)

4 optimization indexes:
- `_file_symbol_map` — O(1) symbol lookup within file
- `_child_to_parent` — O(1) reverse CONTAINS lookup
- `_class_children` — O(1) method lookup within class
- `_sorted_file_nodes` — binary search for enclosing node (O(log N))

#### Completed: Materialized Views (Step 4)

**`kb_agent/views/base.py` — ViewIDMapper + ViewBuilder**
- `ViewIDMapper`: shared lookup indexes (node_by_id, nodes_by_path, edges_by_source/target)
- `group_nodes_by_depth(depth)`: replaces hardcoded `parts[0]` grouping
- `is_utility_name()`: regex-based utility detection (log, config, util, helper, metrics, etc.)
- `sanitize_path()`: path → safe filename for entry IDs

**`kb_agent/views/arch_view.py` — ArchViewBuilder**
- Produces 1 KBEntry (`arch.root`) from graph aggregates
- Language counts, edge counts by kind, entry point detection (main, __init__.py)

**`kb_agent/views/mod_view.py` — ModViewBuilder**
- Configurable depth grouping (`--depth` option)
- Import weighting: business=1.0, utility=0.1, stdlib=0.0
- Utility edge suppression before clustering
- ID format: `mod.{module_key}`

**`kb_agent/views/file_view.py` — FileViewBuilder** (NEW view type)
- 1 entry per unique file path
- Intra-file edge extraction + external dependency listing
- ID format: `file.{sanitized_path}`

**`kb_agent/views/mem_view.py` — MemViewBuilder**
- 1 entry per SymbolNode with outgoing edge info (calls, uses_type)
- Backward-compatible ID format: `mem.{module}.{file}.{parent}.{name}_L{line}`
- Includes parent class name for methods (from CONTAINS edges)

**Model changes:**
- `Layer.FILE = "file"` added to enum
- `KBStats.by_layer` default includes `"file": 0`

**Pipeline changes:**
- `run()` branches: `--with-graph` → materialize views, else → old layers (unchanged)
- `_materialize_views()`: loads graph → creates ViewIDMapper → builds ARCH → MOD → FILE → MEM → links
- `_run_layers()`: wraps old arch/mod/mem layers (backward compat)

#### Completed: Retrieval Engine (Step 5)

**`kb_agent/query/intent.py` — Query Intent Classification**
- `QueryIntent` enum: SYMBOL_LOOKUP, FLOW_TRACE, MODULE_OVERVIEW, RELATIONSHIP, DEFAULT
- `INTENT_BUDGET_RATIOS`: token budget ratios per intent (entry/hop1/hop2/meta)
- `classify_intent()`: keyword-based, specificity-ordered

**`kb_agent/query/mapper.py` — Entry-to-Node Mapping**
- `build_entry_to_node_mapper()`: join FAISS results to graph nodes via (path, line_start)
- Returns None when no graph → graceful fallback to FAISS-only
- Handles collisions by preferring narrower line range

**`kb_agent/query/expander.py` — Graph Expansion**
- `expand_from_seeds()`: bounded BFS from seed nodes using ViewIDMapper indexes
- Bidirectional traversal (outgoing + incoming edges)
- Utility suppression, confidence filtering, max edges per node
- Returns `ExpandedSubgraph` with seed/hop1/hop2 nodes + relevant edges

**`kb_agent/query/composer.py` — Context Composition**
- `compose_context()`: adaptive token budget, 3 detail tiers (full/summary/minimal)
- `RetrievalResult` + `RetrievalMetrics` for instrumentation
- Edge summary formatting, truncation priority (2-hop → 1-hop → entry)

**`kb_agent/query/retrieval.py` — RetrievalEngine Orchestrator**
- Wraps `QueryEngine`, adds graph expansion + context composition
- Lazy `ViewIDMapper` loading, cached across calls
- Graceful fallback: no graph → format FAISS results directly

**CLI:** `query --with-graph` flag added to `scripts/cli.py`

### Phase 2 — Ordered by impact

```
Step 1: Enhanced symbol resolution (biggest impact)
Step 2: Confidence propagation
Step 3: Feature overlay (deterministic)
Step 4: Basic query planner
```

### Phase 3 — Ordered by dependency

```
Step 1: Graph-aware embeddings (prerequisite for others)
Step 2: Cross-language bridging
Step 3: Temporal graph
Step 4: Advanced context composition
Step 5: Hot-path learning (needs runtime integration)
```

---

## 7. Complexity Management Strategy (giải quyết #15)

### 7.1 Nguyên tắc

```
1. Ship 80% accuracy, don't design 100% that never ships
2. Each phase must be independently useful
3. Graph schema changes require migration plan
4. Every new edge kind needs: definition, confidence range, test cases
5. Retrieval quality measured by end-to-end agent task completion
```

### 7.2 Guardrails

```
- Max edge kinds: 10 (current: 6 in MVP)
- Max graph depth for traversal: 3 hops (hard limit)
- Max nodes per query response: 20 (hard limit)
- Feature overlay: optional, can be disabled
- LLM-inferred edges: off by default, opt-in only
- Each phase must pass integration tests before next phase starts
```

### 7.3 Complexity Budget

| Phase | Max New Files | Max New Edge Kinds | Max Lines of Code |
|-------|---------------|-------------------|-------------------|
| MVP | ~15 | 6 | ~3000 |
| Phase 2 | ~10 | +2 | ~2000 |
| Phase 3 | ~15 | +3 | ~4000 |
| Phase 4 | ~10 | +0 | ~3000 |

---

## 8. Migration from Current System

### 8.1 Current → MVP Migration Path

```
Current state:
  - KBEntry model with ARCH/MOD/MEM layers
  - Dotted IDs: "arch.root", "mod.services", "mem.services.auth.login"
  - Parent-child hierarchy only
  - FAISS flat embedding

Migration steps:

1. [DONE] ADD graph models alongside existing models
   - New: SymbolNode, SymbolEdge
   - Keep: KBEntry (used as view output format)
   - No breaking changes

2. [DONE] ADD graph builder after parse step
   - Pipeline: SCAN → PARSE → BUILD_GRAPH → ... → WRITE_VIEWS
   - Graph is built from parser output (same data source)
   - Opt-in via --with-graph flag

3. [DONE] MODIFY mod_layer to use graph for grouping
   - Configurable depth grouping replaces parts[0]
   - Import weighting from graph edges
   - Utility edge suppression

4. [DONE] ADD FILE view between MOD and MEM
   - `FileViewBuilder` produces per-file KBEntry with intra/external edges
   - `Layer.FILE = "file"` added to enum

5. [DONE] MODIFY MEM to receive file context
   - `MemViewBuilder` includes outgoing edge info (calls, uses_type) in LLM prompts
   - Backward-compatible IDs

6. [DONE] MODIFY query engine for graph traversal
   - RetrievalEngine wraps QueryEngine for graph-aware retrieval
   - `query --with-graph` CLI flag, backward-compatible

7. [DONE] UPDATE storage format
   - .kb/graph/ directory created (nodes.jsonl, edges.jsonl, adjacency.json)
   - .kb/entries/ contains arch, mod, file, and mem entries when --with-graph
   - Existing .kb/entries/ kept as-is when --with-graph not set
```

### 8.2 Backward Compatibility

```
- Existing KBEntry format still produced as view output
- Existing FAISS index still works for semantic search
- Existing CLI commands still work
- New features opt-in via CLI flags:
  --with-graph      Enable graph building
  --with-file-view  Enable FILE view
  --depth N         Set grouping depth
```
