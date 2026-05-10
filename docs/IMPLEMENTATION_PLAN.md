# Project Implementation Plan – Knowlegle Base Agent (Knowledge Base Generator)

- Build a **multi‑language via adapter architecture** pipeline that scans a repository, extracts structural information, and generates a searchable knowledge base in Markdown with YAML front‑matter and optional vector embeddings.
- Provide an API for AI agents to query the knowledge graph (symbols, call graph, dependencies) and retrieve context efficiently.
- Support incremental updates when source files change.

## 2. High‑Level Architecture (Revised)
```
AI Agent → Query Interface → Context Provider → Retrieval Contracts → Symbol Graph + CIR (source of truth) → Knowledge Materialization Layer → Views (Markdown, JSON, Mermaid, Embeddings, MCP Responses)
```
**Key Concepts**
1. **Repository Ingestion** – clone repo, detect languages/frameworks, watch file changes.
2. **Language Adapter Architecture** – deterministic parsers (Roslyn, tree‑sitter, Python `ast`, TS Compiler API) are plugged in via adapters, producing **versioned CIR**.
3. **Symbol Graph + CIR** – the **source of truth**.  CIR is split into bounded schemas (symbols, calls, dependencies, architecture) and includes provenance, confidence, and temporal metadata.
4. **Knowledge Materialization Layer** – materializes the graph into consumable views:
   - Markdown documentation (cache layer)
   - Structured JSON/YAML
   - Mermaid diagrams
   - Embeddings for semantic reranking
   - MCP response payloads
5. **Retrieval Engine** – uses a **Retrieval Strategy Layer** (symbol lookup, flow analysis, architectural filtering, semantic reranking) and respects **retrieval contracts** that define query semantics and context budgeting.

### 3. Core Architecture & Orchestration (Revised)
### 3.1 Orchestration Strategy
We will **avoid using CrewAI as the core orchestrator** in the early sprints.  Instead we adopt a **simple, production‑ready pipeline** based on:
* **FastAPI** – HTTP entry points for ingestion, query and context services.
* **Redis Queue** – lightweight task queue for background workers.
* **Background Workers** – deterministic workers (Python processes) that perform parsing, graph updates and retrieval.
This approach eliminates the agent‑centric bottleneck and focuses on **knowledge quality** and **deterministic pipelines**.

### 3.2 CIR Versioning, Bounded Schemas & Entity Identity
*Introduce a versioned Common Intermediate Representation (CIR) split into bounded schemas:* 
```json
{
  "cirVersion": "1.0",
  "language": "csharp",
  "schemas": {
    "symbols": "cir.symbols.v1",
    "calls": "cir.calls.v1",
    "dependencies": "cir.dependencies.v1",
    "architecture": "cir.architecture.v1"
  },
  "entities": [...] 
}
```
Each schema evolves independently (e.g., call‑graph schema may change faster than symbol schema).  Migration scripts handle version upgrades, preserving **graph migration safety**.

**Entity Identity Strategy** – Use a **Fully Qualified Semantic ID** rather than simple method names:
```
repo/project/namespace/class/method(signature)
```
This guarantees uniqueness across overloads, renames, partial classes and generics.

**Provenance & Confidence Metadata** – Every node/edge carries:
```json
{
  "source": "roslyn",
  "confidence": 1.0,
  "generatedAt": "2026-05-10T12:00:00Z",
  "semantic": false,
  "validFrom": "2026-05-01",
  "validTo": null,
  "commitSha": "0631ea7..."
}
```
This enables debugging, trust scoring, and temporal queries.

### 3.3 Separate Symbol & Semantic Graphs (Enhanced)
* **Symbol Graph** – Deterministic, compiler‑grade representation containing classes, methods, imports, calls, inheritance, etc.  This graph is the **source of truth**.
* **Semantic Graph** – AI‑generated, probabilistic layer that adds domain concepts (e.g., "Auth domain", "Billing flow", "Repository pattern").  It is kept **separate** from the Symbol Graph to avoid pollution.

### 3.4 Retrieval Architecture
Add a **Retrieval Strategy Layer** that selects the appropriate mechanism based on query type:
* **Exact Symbol Lookup** – direct node fetch from Symbol Graph.
* **Flow Analysis** – graph traversal following call/import edges.
* **Business Concept Search** – semantic search on the Semantic Graph.
* **Architectural Bounded‑Context Traversal** – respects architectural layers (Presentation, Application, Domain, Infrastructure).
The strategy layer will route queries to the optimal engine and optionally **re‑rank** results using embeddings.

### 3.5 Architectural Boundary Engine
Introduce a component that **understands architectural layers** and filters retrieval results accordingly.  This prevents noise such as migration scripts, test utilities or infra‑only files when querying for a domain flow.

### 3.6 Context Builder Enhancements
* **Context Budgeting** – token budget aware composition.  Nodes are scored using:
  `score = graph_distance_weight + architectural_relevance + semantic_similarity + hot_path_weight`
* **Node Scoring & Dependency Weighting** – prioritize hot paths and high‑relevance symbols.
* **Summarization Fallback** – when budget is exceeded, invoke LLM summarization on overflow nodes.

### 3.7 Observability & Benchmarking
From Sprint 1 we will emit structured logs for:
* Retrieval query type & parameters
* Traversal paths taken
* Context size (tokens) and latency
* Graph cache hits / misses
We will also define a **Gold Benchmark Query Suite** (e.g., find login flow, find callers, explain auth architecture) to continuously measure retrieval quality.

### 3.8 Documentation Output Formats
Generate **both**:
* Human‑readable Markdown for onboarding and review.
* Structured JSON/YAML semantic docs containing `summary`, `dependencies`, `flows`, etc., consumable by AI agents.


## 4. Revised Sprint Roadmap (2‑week sprints)
### Sprint 1 – Core Ingestion, Adapter Architecture & CIR (C# + Roslyn)
  * Set up Python venv, Neo4j container, Redis queue.
  * Implement deterministic Roslyn parser via **adapter** that emits **versioned, bounded CIR**.
  * Ingest repository, build **Symbol Graph** (source of truth) only (no agents).
  * Expose FastAPI endpoint `/ingest` that triggers background workers.
  * Basic observability (logging of ingestion steps, provenance capture).
  * **Deliverable:** Stable Symbol Graph with versioned CIR.
- Set up Python venv, install Neo4j, .NET SDK.
- Implement repo ingestion script (clone, manifest detection, file watcher).
- Build Roslyn wrapper that outputs CIR JSON (entities: class, method, calls).
- Import CIR into Neo4j (nodes Repository → Project → Class → Method, edge CALLS).
- Expose FastAPI endpoints: `GET /symbol/{name}`, `GET /callers/{method}`, `GET /callees/{method}`.
- Write unit test using a small C# sample repo.
**Deliverable:** Running API that returns call‑graph data.

### Sprint 2 – Multi‑Language Parsing, Bounded CIR Schemas & Symbol Graph Enrichment
  * Add parsers for TypeScript (TS Compiler API) and Python (`ast`) via adapters.
  * Extend CIR with **bounded schemas** for calls, dependencies, and architecture.
  * Populate **Symbol Graph** edges: CALLS, IMPORTS, INHERITS, IMPLEMENTS.
  * Provide retrieval APIs: `GET /symbol/{id}`, `GET /callers/{id}`.
  * **Deliverable:** Multi‑language Symbol Graph with reliable retrieval.
- Add parsers for TypeScript (TS Compiler API) and Python (`ast`).
- Extend CIR schema to include inheritance, interface implementation.
- Create edges `INHERITS`, `IMPLEMENTS` in Neo4j.
- Update API with `GET /inheritance/{type}`.
**Deliverable:** Graph with call + inheritance for three languages.

### Sprint 3 – Retrieval Strategy Layer, Weighting & Benchmark Suite
  * Implement the **Retrieval Strategy Layer** with:
    - Symbol lookup
    - Flow analysis
    - Architectural filtering (boundary engine)
    - Dependency weighting (hot‑path vs utility weighting)
    - Semantic reranking (FAISS as reranker, not primary).
  * Define **Gold Benchmark Queries** and automate regression testing.
  * **Deliverable:** High‑quality retrieval with observability metrics.
- Implement Query Planner Agent (rule‑based + LLM fallback).
- Integrate FAISS index for comment/document embeddings.
- Build hybrid retrieval endpoint `POST /search` that combines graph traversal and semantic similarity.
**Deliverable:** Accurate retrieval for queries like “login flow” or “dependency chain”.

### Sprint 4 – Semantic Graph, Materialization & Structured Documentation
  * Build **Semantic Graph** from LLM‑generated annotations (domains, patterns, concepts) with confidence scores.
  * Add **Knowledge Materialization Layer** to produce:
    - Markdown (cache)
    - JSON/YAML semantic docs
    - Mermaid diagrams
    - Embeddings for reranking
    - MCP response payloads
  * Enhance **Context Builder** with token budgeting, dependency weighting, and hot‑path intelligence.
  * **Deliverable:** Enriched knowledge base with dual‑format docs.
- Connect LiteLLM (OpenAI/Claude) for summarization.
- Architecture Agent generates high‑level architecture markdown.
- Flow Analysis Agent produces Mermaid diagrams for request lifecycles.
- Documentation Agent writes per‑node markdown files with front‑matter.
**Deliverable:** Auto‑generated `docs/kb/` hierarchy with rich documentation.

### Sprint 5 – Production‑Ready API, Retrieval Contracts & CI
  * Wrap all services behind a **FastAPI** gateway exposing **Retrieval Contracts** (typed query language).
  * Implement CI pipeline (GitHub Actions) that runs ingestion, retrieval benchmarks, and publishes updated materialized views.
  * No CrewAI orchestration yet – keep the system deterministic.
  * **Deliverable:** Stable, observable service ready for internal consumption.
- Package all agents into an MCP server (FastAPI + OpenAPI spec).
- Provide Graph APIs (`findSymbol`, `findCallers`, `searchSemantic`, …) and Semantic APIs (`explainArchitecture`, `summarizeModule`).
- Add GitHub Actions workflow: on push/PR run scanner, commit updated docs, open PR with changes.
- Publish a small SDK for external AI agents (Claude, Cline, Cursor, OpenHands).
**Deliverable:** Production‑ready service callable by external agents.

## 5. Technology Stack (Updated)
| Layer | Tech |
|-------|------|
| **Core** | Python 3.10+, FastAPI, Docker Compose |
| **Parsers** | Roslyn (C#), TS Compiler API, `ast` (Python), `tree‑sitter` (generic) – accessed via **adapter** layer |
| **Graph Store** | Neo4j (MVP) – optional SQLite edge tables for lightweight mode |
| **Vector Store** | FAISS (local) or Pinecone (cloud) |
| **LLM Gateway** | LiteLLM (OpenAI, Claude, local Llama2) |
| **Orchestration** | Simple FastAPI + Redis Queue pipeline (CrewAI introduced only in later sprints) |
| **Queue** | Redis (task queue) |
| **CI** | GitHub Actions – trigger scanner on PRs |

## 6. Risks & Mitigations (Extended)
- **Parsing diversity** – start with core set (C#, Python, TS) and use `tree‑sitter` for others; keep CIR schema stable.
- **Graph size** – use Neo4j indexing, incremental patch updates, and prune unused nodes.
- **Retrieval quality** – prioritize deterministic graph traversal; use embeddings only as supplemental signal; benchmark with a curated query set.
- **Token overflow** – Context Composer scores relevance, chunks large docs, and uses LLM summarization before feeding context.
- **Incremental updates** – file‑watcher triggers AST diff → graph patch, avoiding full re‑parse.

## 7. Immediate Next Steps (Day 1‑3)
1. **Environment setup** – create venv, install requirements, spin up Neo4j container.
2. **Repository Fingerprinting** – detect architecture style (clean, layered, microservices, event‑driven) during ingestion.
3. **Hot‑Path Intelligence** – compute call‑frequency weights and store as edge attributes.
2. **Repo scanner prototype** – clone a sample C# repo, detect manifests, watch files.
3. **Roslyn parser wrapper** – .NET CLI that outputs CIR JSON (use existing schema `cir_schema_v1.json`).
4. **CIR → Neo4j import script** – Python script using `neo4j` driver to create nodes/edges.
5. **FastAPI skeleton** – endpoints for symbol lookup and call graph.
6. **Write a simple test** – query a known method and verify callers.

## 8. Success Criteria (Enhanced)
- API returns correct symbol and call‑graph data for a sample repo, with provenance and confidence metadata.
- Materialized views (Markdown, JSON, Mermaid) are consistent with the Symbol Graph and respect retrieval contracts.
- Incremental updates preserve temporal validity (`validFrom`/`validTo`) and provenance.
- CI pipeline validates retrieval benchmarks, materialization consistency, and versioned CIR migrations.

---

*Prepared by Cline – senior software engineer.*
