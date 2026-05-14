# Knowlegle Base Agent — Tổng Hợp Ý Tưởng Hệ Thống

## 1. Vision

Knowlegle Base Agent không phải:
- chatbot cho code
- RAG wrapper
- vector search tool
- CrewAI demo project

Mà là:

Repository Intelligence Infrastructure

Hay nói cách khác:

Search Engine + Semantic Operating System for Software Systems

Mục tiêu cuối cùng là:

biến codebase thành structured intelligence

để AI agents có thể:
- hiểu architecture
- hiểu flow
- hiểu dependencies
- retrieve đúng context
- reasoning chính xác
- giảm hallucination
- scale với monorepo lớn

---

## 2. Core Philosophy

System không dựa vào:
- embeddings-first
- prompt magic
- autonomous agents

Mà dựa vào:

deterministic intelligence

Pipeline:

Compiler Intelligence
→ Graph Intelligence
→ Retrieval Intelligence
→ AI Reasoning

LLM chỉ là:
- enrichment layer
- summarization layer
- semantic inference layer

KHÔNG phải source of truth.

---

## 3. Source of Truth

### Symbol Graph + CIR

Đây là trung tâm của toàn bộ hệ thống.

### CIR (Common Intermediate Representation)

Mỗi language parser sẽ normalize về:

versioned bounded schemas

Ví dụ:
- cir.symbols.v1
- cir.calls.v1
- cir.dependencies.v1
- cir.architecture.v1

### CIR chứa:
- entities
- calls
- imports
- inheritance
- DI relations
- architectural metadata
- provenance
- confidence
- temporal metadata

Ví dụ metadata:

```json
{
  "source": "roslyn",
  "confidence": 1.0,
  "generatedAt": "...",
  "commitSha": "...",
  "semantic": false
}
```

---

## 4. Multi-Language Strategy

System KHÔNG “language-agnostic”.

Mà là:

multi-language via adapter architecture

### Mỗi language có adapter riêng

| Language | Technology |
|---|---|
| C# | Roslyn |
| TypeScript | TS Compiler API |
| Python | Python ast |
| Generic fallback | tree-sitter |

### Architecture

Language Adapter
↓
Semantic Extraction
↓
CIR
↓
Symbol Graph

---

## 5. Semantic Extraction > Parsing

AST chỉ hiểu syntax.

Semantic model mới hiểu meaning.

Ví dụ Roslyn hiểu:
- symbol resolution
- interface implementation
- method references
- overloads
- DI relationships
- inheritance
- semantic types

Đây là foundation của:
- call graph
- dependency graph
- architecture reasoning
- retrieval

---

## 6. Symbol Graph vs Semantic Graph

### A. Symbol Graph (Deterministic)

Compiler-grade truth:
- classes
- methods
- imports
- calls
- inheritance
- dependencies

Đây là source of truth.

### B. Semantic Graph (Probabilistic)

AI-generated intelligence:
- Auth Domain
- Billing Flow
- CQRS
- DDD
- architectural patterns

Semantic graph luôn:
- tách biệt
- confidence-scored
- provenance-aware

---

## 7. Knowledge Materialization Layer

Documentation KHÔNG phải source of truth.

Docs chỉ là:

materialized views

### Materializers

Graph
↓
Materialization Layer
├── Markdown
├── JSON
├── YAML
├── Mermaid
├── Embeddings
└── MCP Payloads

---

## 8. Retrieval-Centric Architecture

System optimize:

context correctness

KHÔNG phải generation quality.

### Retrieval Flow

Graph Retrieval
↓
Architectural Filtering
↓
Dependency Weighting
↓
Semantic Reranking
↓
Context Composition

Embeddings KHÔNG phải primary retrieval.

---

## 9. Architectural Boundary Engine

System hiểu:
- Presentation Layer
- Application Layer
- Domain Layer
- Infrastructure Layer

Nhờ đó retrieval:
- giảm noise
- tăng precision
- tránh irrelevant utilities/tests

---

## 10. Context Builder

Component khó nhất của hệ thống.

Nhiệm vụ:
- token budgeting
- node scoring
- dependency weighting
- hot-path prioritization
- summarization fallback
- hierarchical compression

### Scoring Model

score =
graph_distance
+ architectural_relevance
+ semantic_similarity
+ hot_path_weight

---

## 11. Hierarchical Compression

Method Summary
→ Class Summary
→ Module Summary
→ Domain Summary

Giúp:
- giảm token
- scale long-context
- efficient retrieval

---

## 12. Event-Driven Knowledge Pipeline

Architecture dài hạn:

Code Change
→ Event Stream
→ Incremental Analysis
→ Graph Patch
→ Materialization Updates
→ Cache Invalidation

### Example Events
- FileChanged
- SymbolAdded
- MethodRenamed
- DependencyChanged
- ArchitectureDriftDetected

---

## 13. Incremental Intelligence

### Graph Patch Engine

Old CIR
+
New CIR
↓
Graph Diff
↓
Patch Operations

Tránh:
- full reparse
- full graph rebuild

---

## 14. Temporal Intelligence

Mỗi node/edge có:
- validFrom
- validTo
- commitSha

Cho phép:
- graph history
- architecture evolution
- regression analysis
- impact analysis

---

## 15. Repository Ontology Layer

System về lâu dài cần hiểu:
- Aggregate
- Entity
- UseCase
- Gateway
- EventHandler
- Repository Pattern
- CQRS
- DDD

Đây là foundation cho:
- architectural reasoning
- intelligent traversal
- AI understanding

---

## 16. Runtime Intelligence (Future)

Future system sẽ ingest:
- traces
- telemetry
- spans
- runtime frequency

Để build:
- runtime importance
- hot paths
- production flows

---

## 17. Observability & Benchmarking

Metrics:
- retrieval precision
- context compression ratio
- graph latency
- traversal depth
- token usage
- cache hit/miss
- benchmark query success

### Gold Benchmark Queries
- Explain login flow
- Find callers
- Find transaction boundary
- Explain auth architecture

---

## 18. Long-Term Architecture

Eventually system sẽ giống sự kết hợp của:
- Sourcegraph
- CodeQL
- Datadog

cộng thêm:

LLM-aware retrieval intelligence

---

## 19. Final Insight

Bài toán khó nhất KHÔNG phải:
- parser
- graph db
- embeddings
- LLM
- CrewAI

Mà là:

Context Precision

Tức là:

AI phải biết đúng thứ cần biết
không nhiều hơn
không ít hơn

Đó chính là moat kỹ thuật thật sự của toàn bộ hệ thống.
