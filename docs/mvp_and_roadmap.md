# Knowledge Base Agent: MVP & Roadmap

> **Core principle:** Symbol Graph = source of truth. KB = cache/view layer.
> **Optimization target:** Retrieval precision, not document prettiness.
> **ID system:** Stable path-based IDs for overloads, partial classes, rename safety, cross-language consistency.

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
```

#### Graph Ontology (MVP — minimal)

| Edge Kind | Semantics | Example | Default Confidence |
|-----------|-----------|---------|-------------------|
| `imports` | File A imports symbol từ file B | `from auth import login` | 0.95 |
| `inherits` | Class A kế thừa class B | `class Admin(User)` | 0.95 |
| `implements` | Class A implement interface B | `class AuthValidator(IValidator)` | 0.90 |
| `contains` | Class A chứa method B | `AuthMiddleware.validate_token` | 1.00 |
| `calls` | Function A gọi function B | `login()` calls `verify()` | 0.70 |
| `uses_type` | Function A dùng type B trong params/return | `def get_user(id: int) -> User` | 0.80 |

**`calls` confidence thấp nhất vì:**
- Alias imports: `from auth import login as auth_login` → static analysis có thể miss
- Dynamic dispatch: `obj.method()` → không biết `obj` là class nào
- Indirect calls: callbacks, event handlers

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
│     - calls: resolve bằng name matching + scope          │
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

Step 1: Check imports trong file
  → from services.auth_service import login ✅
  → Resolve: repo/services/auth_service.py::login(email, password)
  → Confidence: 0.70 (heuristic, vì có thể là alias hoặc wrong overload)

Step 2: Nếu không tìm thấy trong imports
  → Check symbols trong cùng file
  → Nếu tìm thấy → local call, confidence 0.85

Step 3: Nếu vẫn không tìm thấy
  → Skip edge. KHÔNG guess.
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

Allocation:
  - Entry node (the thing agent asked about): 40% (~1600 tokens)
    → full signature, docstring, behavior, file context
  - 1-hop neighbors (direct relationships): 35% (~1400 tokens)
    → summary + relationship type
  - 2-hop neighbors (indirect relationships): 15% (~600 tokens)
    → name + kind + edge type only
  - Metadata (module, architecture context): 10% (~400 tokens)
```

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
Strategy: hash-based invalidation

1. Store file content hash trong manifest
2. On re-run:
   - Diff file hashes → identify changed files
   - Re-parse only changed files
   - Re-compute nodes/edges for changed files
   - Diff graph: remove old nodes/edges, add new ones
   - Re-materialize affected views:
     * FILE view: only for changed files
     * MEM view: only for symbols in changed files
     * MOD view: only if imports/symbols changed in module
     * ARCH view: only if language counts changed
   - Update FAISS index for affected entries
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

```
Step 1: Data model
  - SymbolNode, SymbolEdge với stable path-based IDs
  - EdgeKind enum (minimal: imports, calls, inherits, implements, contains, uses_type)
  - Confidence metadata
  Files: kb_agent/models/graph.py (NEW)

Step 2: Parser enhancements
  - Extract calls (heuristic, name-matching)
  - Extract type usage (from annotations)
  - Resolve imports to file paths
  Files: kb_agent/parser/python_parser.py, csharp_parser.py, cpp_parser.py

Step 3: Graph builder
  - Build adjacency list from parser output
  - Edge resolution with confidence scoring
  - Store graph as JSONL
  Files: kb_agent/graph/builder.py (NEW)

Step 4: Materialized views
  - ARCH view (from graph, similar to current)
  - MOD view (configurable depth + import weighting)
  - FILE view (NEW: per-file subgraph)
  - MEM view (with file context)
  Files: kb_agent/views/ (NEW directory)

Step 5: Retrieval engine
  - Semantic search (FAISS, same as current)
  - Graph expansion (bounded traversal)
  - Context composition (token budget allocation)
  Files: kb_agent/query/engine.py (MODIFY)

Step 6: Pipeline integration
  - Wire everything together
  - CLI commands updated
  - Incremental update support
  Files: kb_agent/pipeline.py (MODIFY)

Step 7: Tests + validation
  - Graph validation checks
  - Edge confidence validation
  - Retrieval quality tests
  Files: tests/ (MODIFY)
```

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

1. ADD graph models alongside existing models
   - New: SymbolNode, SymbolEdge
   - Keep: KBEntry (used as view output format)
   - No breaking changes

2. ADD graph builder after parse step
   - Pipeline: SCAN → PARSE → BUILD_GRAPH → ... → WRITE_VIEWS
   - Graph is built from parser output (same data source)

3. MODIFY mod_layer to use graph for grouping
   - Replace parts[0] grouping with graph-based clustering
   - Import weighting from graph edges

4. ADD FILE view between MOD and MEM
   - New view type, doesn't break existing MEM

5. MODIFY MEM to receive file context
   - FILE view output feeds into MEM analysis

6. MODIFY query engine for graph traversal
   - Add graph expansion step after semantic search

7. UPDATE storage format
   - Add .kb/graph/ directory
   - Add .kb/views/file/ directory
   - Existing .kb/entries/ can be migrated or kept
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
