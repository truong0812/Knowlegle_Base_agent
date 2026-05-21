# Knowledge Base Agent — Kiến Trúc Hệ Thống

> **Core principle:** Symbol Graph = source of truth. KB = cache/view layer.
> **Optimization target:** Context precision, không phải document prettiness.
> **ID system:** Stable path-based IDs cho overloads, partial classes, rename safety, cross-language consistency.

---

## 1. Tổng Quan Kiến Trúc

Knowledge Base Agent biến source code thành structured knowledge qua pipeline deterministic:

```text
Canonical Runtime Model:

Scanner → Parser → Graph Builder → Materialized Views → FAISS Index → Retrieval Engine
                                  ↘ Feature Overlay
                                  ↘ Hot-Path Scoring
                                  ↘ Temporal Snapshots
                                  ↘ Cross-Language Bridges
                                  ↘ Runtime Telemetry
```

Symbol Graph là trung tâm — source of truth duy nhất. Mọi thứ khác (KB entries, embeddings, context) là materialized views sinh ra từ graph.

### Lớp trí tuệ

```text
Compiler Intelligence   ← parser, AST, tree-sitter
  → Graph Intelligence  ← symbol graph, confidence, edges
  → Retrieval Intelligence ← intent, expansion, ranking
  → AI Reasoning        ← LLM enrichment (không phải source of truth)
```

LLM chỉ là lớp enrichment: tóm tắt, diễn giải, gợi ý semantic. Mọi semantic inference phải có confidence và provenance.

---

## 2. Symbol Graph — Source of Truth

### SymbolNode

```python
class SymbolNode:
    id: str           # Stable path-based ID
    kind: SymbolKind  # class, function, method, interface, ...
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

### SymbolEdge

```python
class SymbolEdge:
    source: str        # Node ID
    target: str        # Node ID
    kind: EdgeKind     # imports, calls, inherits, implements, contains, uses_type, bridges_to
    confidence: float  # 0.0 - 1.0
    source_type: str   # "deterministic", "heuristic", "inferred"
    resolution: str    # HOW edge was resolved — determines confidence
```

### ID Format

```
repo/{relative_path}::{ScopeName.}SymbolName({param_types})
```

Ví dụ:

| Symbol | ID |
|--------|-----|
| Top-level function `login` trong `auth.py` | `repo/src/auth.py::login(email, password)` |
| Method `validate_token` trong class `AuthMiddleware` | `repo/src/middleware/auth.py::AuthMiddleware.validate_token(token: str)` |
| Overloaded method `process` (2 overloads) | `repo/src/handler.py::Handler.process(data: dict)` và `...Handler.process(data: str, format: str)` |
| C# partial class `UserService` | `repo/Services/UserService.cs::UserService` và `repo/Services/UserService.Helpers.cs::UserService` |

**Tại sao path-based ID:**

| Vấn đề | Giải pháp |
|---------|-----------|
| Overloads (cùng tên, khác params) | Signature included trong ID |
| Partial classes (C#) | File path khác nhau → ID khác nhau |
| Rename symbol | Path stable → chỉ cần re-resolve symbol name |
| Cross-language | Extension trong path → language rõ ràng |
| Dedup | Line number fallback nếu signature trùng |

### Graph Ontology

| Edge Kind | Semantics | Default Confidence |
|-----------|-----------|-------------------|
| `imports` | File A imports symbol từ file B | 0.95 |
| `inherits` | Class A kế thừa class B | 0.95 |
| `implements` | Class A implement interface B | 0.90 |
| `contains` | Class A chứa method B | 1.00 |
| `calls` | Function A gọi function B | Graduated (xem bảng dưới) |
| `uses_type` | Function A dùng type B trong params/return | 0.80 |
| `bridges_to` | Cross-language bridge (HTTP, data contract, message queue) | 0.30–0.75 |

---

## 3. Graduated Confidence System

`resolution` field là khóa để graduate confidence. Thay vì gán 1 giá trị flat cho mỗi edge kind, confidence được xác định bởi **cách resolve** dẫn đến edge đó.

### 3-tier Resolution Hierarchy

```text
1. DETERMINISTIC (confidence: 0.90-1.00)
   - Tree-sitter/AST extract trực tiếp
   - imports, inherits, implements, contains
   - Không ambiguity

2. HEURISTIC (confidence: 0.50-0.89)
   - calls: confidence graduated theo resolution method
   - uses_type: từ type annotations
   - bridges_to: từ protocol/name matching
   - Có thể sai nếu alias/overload

3. INFERRED (confidence: 0.00-0.49)
   - calls qua LLM analysis
   - cross-file relationships không resolve được
   - Chỉ dùng khi không có deterministic/heuristic

RULE: Thà thiếu edge còn hơn edge sai.
Edge có confidence < 0.50: KHÔNG thêm vào graph.
```

### Graduated `calls` Confidence

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

### Confidence Propagation

```text
Node confidence:
  - Base: 1.0 (deterministic) or LLM-assigned
  - Incoming edge bonus: if 3+ high-confidence edges → boost confidence
  - Decay: confidence decreases with distance from verified source

Edge confidence (query-time):
  hop 0: full confidence
  hop 1: confidence × 0.8
  hop 2: confidence × 0.6
  hop 3+: không traverse (cut off)

Propagated confidence:
  node_confidence = base_confidence × (1 + edge_bonus)
  edge_effective_confidence = base_confidence × decay_factor
```

---

## 4. Knowledge Materialization

KB entries không phải source of truth. Chúng là **materialized views** sinh ra từ graph để phục vụ retrieval.

### 4 View Types

| View | Câu hỏi trả lời | ID format |
|------|-----------------|-----------|
| `arch` | "Dự án này làm gì?" | `arch.root` |
| `mod` | "Module X chứa gì? Public API?" | `mod.{module_key}` |
| `file` | "File X chứa symbols gì? Liên quan nhau thế nào?" | `file.{sanitized_path}` |
| `mem` | "Symbol X làm gì cụ thể?" | `mem.{module}.{file}.{parent}.{name}_L{line}` |

### Configurable Depth (MOD view)

```text
depth=1: src/                    → module "src"
depth=2: src/services/           → module "src/services"
depth=3: src/services/auth/      → module "src/services/auth"
```

### Import Weighting

```text
Edge weight rules:
  - business logic imports  → weight 1.0 (auth, user, payment)
  - standard library imports → weight 0.0 (os, sys, logging)
  - utility imports         → weight 0.1 (helpers, utils, config)
  - test imports            → weight 0.0

Clustering chỉ dùng edges có weight >= 0.5
→ Tránh "giant connected component" từ utility files
```

### Feature Overlay (Phase 2)

Feature detection deterministic, không dùng LLM clustering:

1. Extract noun clusters từ symbol names
2. Group symbols sharing nouns
3. Merge overlapping features (≥50% overlap)
4. Name features by shared noun

Kết quả: `feature` entries materialized từ graph-density clusters, hoàn toàn deterministic.

---

## 5. Retrieval Engine

### Pipeline

```text
Query
  → intent detection
  → semantic seed search (FAISS)
  → graph expansion (bounded BFS)
  → architecture filtering
  → confidence-aware ranking
  → context composition
```

### Intent Types

| Intent | Keyword hints | Strategy |
|--------|--------------|----------|
| `SYMBOL_LOOKUP` | "what does", "explain" | Seed node + 1-hop context |
| `FLOW_TRACE` | "how does", "flow", "process" | Entry point → calls chain |
| `MODULE_OVERVIEW` | "what's in", "overview" | Module entry + FILE views |
| `RELATIONSHIP` | "what uses", "depends on", "callers" | Reverse graph traversal |
| `CHAIN_TRACE` | "call chain from X to Y" | Causal chain via CALLS edges |
| `VERSION_DIFF` | "what changed", "diff" | Temporal graph diff |
| `DEFAULT` | fallback | SYMBOL_LOOKUP strategy |

### Traversal Budget

```text
Max hops: 2 (hoặc 4 cho chain tracing)
Max nodes: 15
Max edges per node: 5
Confidence threshold: >= 0.60
Utility suppression: logging, metrics, config, serialization → skip
```

### Adaptive Token Budget

```text
Base budget: ~4000 tokens per query

Query intent factor — ratio thay đổi theo loại query:
  SYMBOL_LOOKUP → entry: 60%, hop1: 20%, hop2: 10%, meta: 10%
  FLOW_TRACE    → entry: 25%, hop1: 45%, hop2: 20%, meta: 10%
  RELATIONSHIP  → entry: 30%, hop1: 40%, hop2: 20%, meta: 10%
  Default       → entry: 40%, hop1: 35%, hop2: 15%, meta: 10%

Per-node cap: max 500 tokens/node
Truncation priority: hop2 → hop1 → entry (luôn giữ signature)
```

### Embedding Strategy

```text
Embedding target: AI summary text của mỗi node
  - Nếu có ai.summary → embed summary
  - Nếu không → embed signature
  - Nếu không có signature → embed "{kind} {name}"

Graph-aware embeddings (Phase 3):
  - MEM entry embedding text enriched với: calls made, callers, feature membership, hotness score
  - Non-MEM entries giữ plain text embeddings
```

---

## 6. Multi-Language Strategy

Hệ thống KHÔNG "language agnostic". Mỗi ngôn ngữ có adapter riêng để tận dụng semantic tốt nhất:

| Ngôn ngữ | Adapter dài hạn | Fallback hiện tại |
|---|---|---|
| C# | Roslyn | tree-sitter |
| TypeScript | TS Compiler API | tree-sitter (tương lai) |
| Python | Python `ast` | tree-sitter |
| C++ | clang tooling (tương lai) | tree-sitter |

### CIR: Common Intermediate Representation

Mỗi adapter normalize dữ liệu về versioned bounded schemas:

```text
cir.symbols.v1
cir.calls.v1
cir.dependencies.v1
cir.architecture.v1
```

CIR chứa: entities, calls, imports, inheritance, interface implementation, type usages, dependency relations, provenance, confidence, temporal metadata.

```text
Language Adapter → Semantic Extraction → CIR → Symbol Graph
```

### Semantic Extraction > Parsing

AST chỉ hiểu syntax. Semantic model (như Roslyn) mới hiểu meaning: symbol resolution, interface implementation, method references, overloads, DI relationships, inheritance, semantic types. Đây là foundation của call graph, dependency graph, architecture reasoning.

---

## 7. Cross-Language Bridging

Phân tích tĩnh không resolve được inter-language calls. Ba chiến lược bridge:

| Strategy | Cách detect | Confidence |
|----------|-------------|------------|
| `HttpApiBridge` | HTTP route decorators/attributes match URL paths | 0.50–0.75 |
| `DataContractBridge` | Shared DTO class names giữa languages, boosted by field similarity | 0.40–0.70 |
| `MessageQueueBridge` | Shared topic/channel names trong node names/docstrings | 0.30–0.60 |

- `BridgeDetector` orchestrate các strategies với deduplication
- Edge kind: `BRIDGES_TO` (confidence 0.30–0.75)
- `bridge_metadata` field trên SymbolEdge stores protocol và route info
- Activated via `--detect-bridges` flag

---

## 8. Temporal Graph

Versioned snapshots tại commit boundaries:

```text
.kb/graph/versions/<version_id>/
  nodes.jsonl
  edges.jsonl
  adjacency.json
```

- Auto-detects git commit hash cho version labels
- `versions` CLI command lists stored versions
- `diff` CLI command shows node/edge diffs giữa versions
- `VERSION_DIFF` query intent cho temporal queries
- Cho phép: graph history, architecture evolution, regression analysis, impact analysis

---

## 9. Runtime Intelligence

### OpenTelemetry Trace Ingestion

`TelemetryIngestor` maps trace spans to graph nodes. `TelemetryStorage` persists traces dưới `.kb/telemetry/`. `update-runtime-metadata` aggregate call counts, latency, error-rate metadata.

```text
traces.json → ingest-telemetry → .kb/telemetry/ → update-runtime-metadata → runtime_metadata.json
```

### Hot-Path Scoring

Nodes ranked by incoming CALLS edge count, normalized to 0.0–1.0 hotness. Static heuristic (không cần runtime data): entry points + symbols được gọi nhiều = high weight.

### Self-Tuning Retrieval

Feedback-based parameter adjustment:

```text
feedback.jsonl → train-ranking-model → tuning_config.json → auto-tune → retrieval loads overrides tự động
```

Heuristic ranking model: adjust edge weights, hop limits, suppression rules dựa trên feedback data.

### Multi-Repo Federation

`FederatedGraphManager` với cross-repo resolution:

- Namespaced foreign nodes (tránh ID collisions)
- `REFERENCES_REPO` edges cho cross-repo traversal
- `add-repo` register external graph, `resolve-cross-repo` persist foreign nodes
- Graph cleanup on repo removal, dedup against current edges

### Observability Dashboard

Graph health metrics + retrieval analytics:

- Node/edge counts, confidence distribution, orphan-node ratio
- Bridge và cross-repo edge counts
- Feedback volume, useful-feedback rate
- `dashboard`, `graph-health`, `query-analytics` CLI commands

---

## 10. Design Rationale

### Context Precision là bài toán khó nhất

Bài toán khó nhất không phải parser, graph database, embeddings hay LLM. Bài toán khó nhất là **context precision**: AI agent chỉ thật sự hữu ích khi biết đúng thứ cần biết, vào đúng thời điểm, với đúng mức chi tiết.

### Scoring Model

```text
score = graph_distance
      + architectural_relevance
      + semantic_similarity
      + hot_path_weight
```

### Symbol Graph vs Semantic Graph

**Symbol Graph (Deterministic)** — Compiler-grade truth: classes, methods, imports, calls, inheritance, dependencies. Đây là source of truth.

**Semantic Graph (Probabilistic)** — AI-generated intelligence: Auth Domain, Billing Flow, CQRS, DDD, architectural patterns. Luôn tách biệt, confidence-scored, provenance-aware.

### Hierarchical Compression

```text
Method Summary → Class Summary → Module Summary → Domain Summary
```

Giảm token, scale long-context, efficient retrieval.

### Architectural Boundary Engine

System hiểu Presentation → Application → Domain → Infrastructure layers. Retrieval giảm noise, tăng precision, tránh irrelevant utilities/tests.

---

## 11. Complexity Management

### Guardrails

```text
- Max edge kinds: 10 (hiện tại: 7)
- Max graph depth for traversal: 3 hops (hard limit)
- Max nodes per query response: 20 (hard limit)
- Feature overlay: optional, có thể disable
- LLM-inferred edges: off by default, opt-in only
- Mỗi phase phải pass integration tests trước khi phase tiếp theo bắt đầu
```

### Complexity Budget

| Phase | Files mới | Edge Kinds mới | Lines of Code |
|-------|-----------|----------------|---------------|
| Phase 1 (MVP) | ~15 | 6 | ~3000 |
| Phase 2 | ~10 | +0 | ~2000 |
| Phase 3 | ~15 | +1 (BRIDGES_TO) | ~4000 |
| Phase 4 | ~10 | +0 | ~2240 |

### Nguyên tắc

1. Ship 80% accuracy, không design 100% mà không bao giờ ship
2. Mỗi phase phải độc lập hữu dụng
3. Graph schema changes require migration plan
4. Mỗi edge kind mới cần: definition, confidence range, test cases
5. Retrieval quality measured by end-to-end agent task completion
6. Không mở rộng complexity nếu chưa có benchmark chứng minh retrieval tốt hơn

---

## 12. Hướng Dài Hạn (chưa implement)

### Event-Driven Knowledge Pipeline

```text
Code Change → Event Stream → Incremental Analysis → Graph Patch → Materialization Updates → Cache Invalidation
```

Events: FileChanged, SymbolAdded, MethodRenamed, DependencyChanged, ArchitectureDriftDetected.

### Incremental Intelligence

```text
Old CIR + New CIR → Graph Diff → Patch Operations
```

Tránh full reparse và full graph rebuild.

### Repository Ontology Layer

System hiểu: Aggregate, Entity, UseCase, Gateway, EventHandler, Repository Pattern, CQRS, DDD. Foundation cho architectural reasoning, intelligent traversal, AI understanding.

### Temporal Intelligence

Mỗi node/edge có `validFrom`, `validTo`, `commitSha`. Cho phép graph history, architecture evolution, regression analysis, impact analysis.

### Aspiration

Eventually system sẽ giống sự kết hợp của Sourcegraph + CodeQL + Datadog cộng thêm LLM-aware retrieval intelligence.
