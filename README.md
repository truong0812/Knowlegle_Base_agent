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

```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Analyze a repository
kb-agent analyze --repo /path/to/repo --out .kb

# Query the knowledge base
kb-agent query "How does user registration work?"
```

## Đánh giá chất lượng

| Metric | Cách đo | Mục tiêu |
|---|---|---|
| Coverage | % symbols parse thành công | ≥ 90% |
| Signature accuracy | KB signature vs actual code | ≥ 95% |
| Consistency | Parent-child đúng hierarchy | 100% |
| Hallucination rate | Random sample, human check | ≤ 5% |

## Trạng thái dự án

**Pre-MVP** — đang thiết kế. Xem chi tiết tại [docs/MVP.md](docs/MVP.md).

## License

MIT
