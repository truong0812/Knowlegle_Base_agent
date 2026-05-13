# MVP Design — Knowledge Base Agent

Mục tiêu MVP: phân tích codebase Python/C#/C++ thành knowledge base có cấu trúc, phục vụ các AI agent khác query.

---

## 1. Kiến trúc tổng thể

```
┌─────────────┐
│  Repository  │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│            Scanner & Language Detector        │
│  - Quét files, detect ngôn ngữ per-file      │
│  - Respect .kbignore                          │
│  - Output: file manifest (files.json)         │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│              Layer 1 — Architecture           │
│  Input: file manifest + folder structure      │
│  Parser: manifest analysis, import scanning   │
│  LLM: summarize repo purpose, entry points    │
│  Output: architecture entries (layer=arch)    │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│              Layer 2 — Module                 │
│  Input: source files per module + L1 results  │
│  Parser: tree-sitter AST → public symbols     │
│  LLM: summarize module purpose, API surface   │
│  Output: module entries (layer=mod)           │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│           Layer 3 — Unit/Member               │
│  Input: individual class/function + L2 result │
│  Parser: tree-sitter → signature, params      │
│  LLM: summarize behavior, purpose             │
│  Output: member entries (layer=mem)           │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│         Indexer & Validator                   │
│  - Compute embeddings (sentence-transformers) │
│  - Build FAISS index                          │
│  - Run consistency checks                     │
│  - Output quality report                      │
└──────────────────────────────────────────────┘
```

---

## 2. Data Schema

### Entry schema (chung cho mọi layer)

```json
{
  "id": "<dotted.path.to.symbol>",
  "layer": "arch | mod | mem",
  "parent": "<parent-id | null>",
  "children": ["<child-id>", ...],

  "static": {
    // Deterministic — đến từ parser/AST
    "kind": "method | class | module | package | function | ...",
    "language": "python | csharp | cpp",
    "path": "relative/path/to/file",
    "line_start": 45,
    "line_end": 62,
    "signature": "...",
    "modifiers": [...],
    "parameters": [...],
    "return_type": "...",
    "docstring": "...",
    "imports": [...],
    "source": "ast"
  },

  "ai": {
    // Probabilistic — đến từ LLM
    "summary": "1-2 câu tóm tắt",
    "purpose": "mục đích trong context lớn hơn",
    "behavior": ["bước 1", "bước 2"],
    "tags": ["tag1", "tag2"],
    "dependencies": ["symbol-id khác"],
    "confidence": 0.0 - 1.0,
    "source": "llm"
  }
}
```

### Layer-specific fields

**Layer 1 — Architecture (`layer: "arch"`)**
```json
{
  "static": {
    "kind": "package",
    "entry_files": ["src/main.py", "src/Program.cs"],
    "manifests": ["pyproject.toml", "package.json"],
    "languages": ["python", "csharp"],
    "total_files": 142,
    "directory_structure": { ... }
  },
  "ai": {
    "summary": "E-commerce backend with REST API and payment processing",
    "purpose": "...",
    "tags": ["web-api", "e-commerce", "payment"],
    "confidence": 0.9
  }
}
```

**Layer 2 — Module (`layer: "mod"`)**
```json
{
  "static": {
    "kind": "module",
    "files": ["src/services/user_service.py", "src/services/auth.py"],
    "exports": ["UserService", "AuthService", "create_user"],
    "imports_external": ["django", "requests"],
    "imports_internal": ["myapp.models", "myapp.config"]
  },
  "ai": {
    "summary": "User management module handling registration, auth, and profile",
    "purpose": "Core user lifecycle management for the application",
    "tags": ["user-management", "authentication"],
    "confidence": 0.88
  }
}
```

**Layer 3 — Member (`layer: "mem"`)**
```json
{
  "static": {
    "kind": "method",
    "signature": "def create_user(name: str, email: str) -> User",
    "parameters": [
      {"name": "name", "type": "str"},
      {"name": "email", "type": "str"}
    ],
    "return_type": "User",
    "modifiers": [],
    "docstring": "Creates a new user..."
  },
  "ai": {
    "summary": "Validates input, checks for duplicate email, creates user record",
    "behavior": ["Validate name and email format", "Query DB for existing email", "Hash password", "Insert user record", "Return created User object"],
    "tags": ["crud", "user", "validation"],
    "confidence": 0.82
  }
}
```

---

## 3. Parser Strategy

Tree-sitter là parser thống nhất cho cả 3 ngôn ngữ:

| Ngôn ngữ | Tree-sitter grammar | Notes |
|---|---|---|
| Python | `tree-sitter-python` | Fallback: built-in `ast` module |
| C# | `tree-sitter-c-sharp` | |
| C++ | `tree-sitter-cpp` | Macros/templates chỉ extract được declaration |

### Extract pipeline per file

```
Source file → tree-sitter parse → AST
  → walk AST, extract:
    - class/struct/interface declarations → kind: "class"
    - function/method declarations → kind: "method" or "function"
    - import/using statements → imports
    - namespace/package declarations → hierarchy
  → emit chunks, mỗi chunk = 1 symbol
```

---

## 4. LLM Strategy

### Quy tắc chung

- Mỗi layer gọi LLM **với context bounded**:
  - Layer 1: folder structure + manifests (< 2K tokens)
  - Layer 2: list of public symbols từ parser + L1 summary (< 4K tokens)
  - Layer 3: 1 function/class source + L2 summary (< 4K tokens)
- **Cache mọi LLM response** keyed by (file hash + prompt hash)
- Batch processing: gọi LLM cho nhiều entries cùng layer song song

### Prompt templates

**Layer 1 — Architecture**
```
System: You are analyzing a codebase. Based on the file structure and manifests below,
produce a JSON with: summary (1-2 sentences), purpose, tags, entry_points.

Context: {folder_tree}
Manifests: {manifest_contents}
```

**Layer 2 — Module**
```
System: You are analyzing a code module. Based on the symbols and parent architecture below,
produce a JSON with: summary, purpose, tags.

Architecture context: {layer1_summary}
Symbols in this module: {symbol_list}
File contents: {source_snippet}
```

**Layer 3 — Member**
```
System: You are analyzing a single function/method. Produce a JSON with:
summary (1 sentence), behavior (list of steps), tags, confidence (0-1).

Module context: {layer2_summary}
Source code:
{source_code}
```

---

## 5. Validation & Quality

### Tự động (chạy sau pipeline)

| Check | Logic |
|---|---|
| Signature match | Re-parse file, so sánh signature trong KB vs AST |
| Parent consistency | `entry.parent` phải tồn tại, `entry.layer` phải đúng thứ tự (mem < mod < arch) |
| Orphan detection | Entry trong KB nhưng symbol không còn trong codebase |
| Completeness | % symbols trong codebase có entry trong KB |

### Human review

- Sinh report: danh sách entries có `confidence < 0.7`, sắp xếp theo confidence tăng dần
- Reviewer check random sample (N entries), đánh giá: summary đúng/sai/thiếu

---

## 6. Output Layout

```
.kb/
├── entries/                                    # 1 JSON file per entry
│   ├── arch.myapp.json                         # Layer 1
│   ├── mod.myapp.services.json                 # Layer 2
│   ├── mod.myapp.models.json
│   ├── mem.myapp.services.userservice.json     # Layer 3 (class)
│   ├── mem.myapp.services.userservice.createuser.json  # Layer 3 (method)
│   └── ...
├── index/
│   └── faiss.index                             # Vector index
├── manifest.json                               # KB metadata (languages, stats, version)
└── quality_report.json                         # Validation results
```

**manifest.json**
```json
{
  "version": "1.0",
  "source_repo": "/path/to/repo",
  "source_commit": "abc123",
  "languages": ["python", "csharp", "cpp"],
  "stats": {
    "total_entries": 342,
    "by_layer": {"arch": 1, "mod": 12, "mem": 329},
    "coverage": 0.93,
    "avg_confidence": 0.84
  },
  "created_at": "2026-05-13T10:00:00Z"
}
```

---

## 7. Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| CLI | Typer |
| Parser | tree-sitter (unified), Python `ast` (fallback) |
| LLM | OpenAI API (hoặc local model) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector Index | FAISS |
| QA Endpoint | FastAPI |
| Config | pydantic, python-dotenv |

---

## 8. Milestones

### M0 — Scaffold & Scanner (hiện tại)
- Repo structure, CLI stub, scanner + language detector
- Deliverable: `kb-agent scan` hoạt động
- Acceptance: files.json sinh ra đúng trên sample repo

### M1 — Tree-sitter Parser (3 ngày)
- Integrate tree-sitter cho Python, C#, C++
- Extract: classes, functions, imports, namespaces
- Deliverable: `kb-agent parse` sinh ra raw chunks
- Acceptance: ≥90% top-level symbols được extract trên sample repos

### M2 — Layered Analysis Pipeline (5 ngày)
- Implement 3-layer pipeline (Architecture → Module → Member)
- LLM integration cho từng layer
- Deliverable: `kb-agent analyze` sinh ra entries JSON đầy đủ
- Acceptance: entries có cả `static` và `ai` fields, parent-child đúng

### M3 — Validation & Quality (3 ngày)
- Auto-validator: signature check, consistency check, coverage
- Quality report generation
- Deliverable: `kb-agent validate` sinh ra quality_report.json
- Acceptance: coverage ≥90%, consistency 100%

### M4 — Indexer & QA Endpoint (3 ngày)
- Compute embeddings, build FAISS index
- FastAPI endpoint: query → retrieve top-k relevant entries
- Deliverable: `kb-agent query` + HTTP API
- Acceptance: top-3 relevant với precision ≥0.7

### M5 — Polish & Testing (2 ngày)
- End-to-end test trên 3 sample repos (1 Python, 1 C#, 1 C++)
- CLI documentation
- Error handling, logging

**Total: ~16 ngày (1 engineer)**

---

## 9. Sample Repos cho Testing

| Ngôn ngữ | Repo gợi ý | Lý do |
|---|---|---|
| Python | FastAPI source hoặc Flask | Medium size, well-structured |
| C# | ASP.NET Core sample | Typical enterprise structure |
| C++ | Một project opensource nhỏ (ví dụ: tree-sitter itself) | Headers, templates, namespaces |
