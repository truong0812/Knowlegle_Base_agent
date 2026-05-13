# Knowledge Base Agent

**Codebase → Structured Knowledge Base**, phục vụ các AI agent khác tra cứu và reasoning về code.

## Vấn đề

Khi một AI agent cần hiểu codebase (ví dụ: code review agent, debugging agent, onboarding agent), nó phải tự đọc và phân tích source code — tốn context, dễ sai, không tái sử dụng được.

**Knowledge Base Agent** giải quyết bằng cách **phân tích codebase một lần, sinh ra knowledge base có cấu trúc** mà các agent khác có thể query.

## Cách tiếp cận: Layered Analysis

Thay vì ném toàn bộ codebase vào LLM (→ hallucination), agent phân tích theo **3 layer**, mỗi layer có context giới hạn và kết quả layer trên làm input cho layer dưới:

```
Layer 1 — Architecture (repo-level)
  Input: folder structure, manifests, file list
  Output: packages, entry points, module dependency map

Layer 2 — Module (file/folder-level)
  Input: source code của 1 module + kết quả Layer 1
  Output: public API surface (classes, interfaces, exports)

Layer 3 — Unit/Member (class/function-level)
  Input: 1 class/function + kết quả Layer 2
  Output: signature, behavior, summary
```

Mỗi entry trong KB tách rõ nguồn dữ liệu:

- **`static`**: đến từ parser (AST) — deterministic, có thể verify tự động
- **`ai`**: đến từ LLM — cần confidence score, có thể review

## Ngôn ngữ MVP

| Ngôn ngữ | Parser | Lý do chọn |
|---|---|---|
| **Python** | `ast` + tree-sitter | Built-in AST, dễ bắt đầu |
| **C#** | tree-sitter | Ngôn ngữ enterprise phổ biến |
| **C++** | tree-sitter | Hard case — validate thiết kế |

## Output

```
.kb/
├── entries/                    # JSON entries, mỗi symbol 1 file
│   ├── arch.myapp.json
│   ├── mod.myapp.services.json
│   └── mem.myapp.services.userservice.createuser.json
├── index/                      # FAISS vector index
│   └── faiss.index
└── manifest.json               # Metadata toàn KB
```

Mỗi entry có schema:

```json
{
  "id": "myapp.services.userservice.createuser",
  "layer": "member",
  "parent": "myapp.services.userservice",

  "static": {
    "signature": "public User CreateUser(string name, string email)",
    "path": "src/Services/UserService.cs",
    "language": "csharp",
    "line_start": 45,
    "line_end": 62,
    "kind": "method",
    "modifiers": ["public", "async"],
    "parameters": [
      {"name": "name", "type": "string"},
      {"name": "email", "type": "string"}
    ],
    "return_type": "User"
  },

  "ai": {
    "summary": "Creates a new user with validation and sends welcome email",
    "purpose": "Entry point for user registration flow",
    "behavior": ["Validate input", "Check duplicate email", "Persist user", "Send welcome email"],
    "tags": ["user-management", "registration"],
    "confidence": 0.85
  }
}
```

## Quick Start

**Yêu cầu**: Python 3.10+

```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Scan — Liệt kê source files

```bash
python -m scripts.cli scan --repo /path/to/repo
```

Output:
```
Found 38 source files in /path/to/repo
  python   src/services/user_service.py
  csharp   src/Services/UserService.cs
  cpp      src/core/engine.cpp
```

### Parse — Trích xuất symbols

```bash
python -m scripts.cli parse --repo /path/to/repo
```

Output:
```
src/services/user_service.py (python):
  class      L  7-24  UserService
             class UserService
  function   L 13-17  create_user
             def create_user(name: str, email: str) -> dict
  import     typing (Optional)
```

### Analyze — Full pipeline (3 layers)

```bash
# Static analysis only (không cần OpenAI API key)
python -m scripts.cli analyze --repo /path/to/repo --out .kb --skip-ai

# Với LLM enrichment (cần OPENAI_API_KEY env var)
python -m scripts.cli analyze --repo /path/to/repo --out .kb
```

Output:
```
Analysis complete: 205 entries
  Layers: {'arch': 1, 'mod': 3, 'mem': 201}
  Languages: python, csharp, cpp
  Output: .kb
```

### Validate — Kiểm tra chất lượng KB

```bash
python -m scripts.cli validate --kb .kb
```

Output:
```
Validation report for .kb:
  Total entries: 205
  Consistency: 100%
  [PASS] parent_consistency: All parents consistent
  [PASS] orphan_detection: No orphans
```

### Query — Semantic search (cần sentence-transformers + faiss-cpu)

```bash
pip install sentence-transformers faiss-cpu
python -m scripts.cli query "How does user registration work?" --kb .kb
```

### CLI flags

| Command | Flag | Mô tả |
|---|---|---|
| `analyze` | `--skip-ai` | Chỉ static analysis, không gọi LLM |
| `analyze` | `--model gpt-4o-mini` | Chọn model LLM |
| `query` | `--top-k 3` | Số kết quả trả về |

## Đánh giá chất lượng

| Metric | Cách đo | Mục tiêu |
|---|---|---|
| Coverage | % symbols parse thành công | ≥ 90% |
| Signature accuracy | KB signature vs actual code | ≥ 95% |
| Consistency | Parent-child đúng hierarchy | 100% |
| Hallucination rate | Random sample, human check | ≤ 5% |

## Trạng thái dự án

**MVP hoàn tất** — scanner, parser (Python/C#/C++), 3-layer analysis pipeline, validator, CLI đều hoạt động. 41 tests passing. Xem chi tiết tại [docs/MVP.md](docs/MVP.md) và [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

## License

MIT
