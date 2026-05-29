# Learning UI MVP — Implementation Phases

> **Goal:** Break MVP Plan thành 5 phase nhỏ, mỗi phase deploy được, test được, và có giá trị độc lập.
> Tổng ước tính: ~11-15h

## Phase Overview

```text
Phase 1 (Backend + Refactor)
  → Phase 2 (Frontend Views) ──┐
  → Phase 3 (Chat Backend) ────┤  ← Phase 2 & 3 có thể song song
                                ↓
                          Phase 4 (Chat Frontend)
                                ↓
                          Phase 5 (Testing + Polish)
```

| Phase | Nội dung chính | Files chính | Ước tính |
|-------|---------------|-------------|----------|
| **1** | API Foundation + Static split | server.py, styles.css, app.js, index.html | ~2-3h |
| **2** | Overview + Feature Views | app.js, styles.css, index.html | ~2-3h |
| **3** | Chat Backend | chat.py, server.py | ~3-4h |
| **4** | Chat Panel + Integration | app.js, styles.css, index.html | ~2-3h |
| **5** | Testing + Polish | test_dashboard_server.py, test_dashboard_chat.py | ~2h |

---

## Phase 1: Backend API Foundation + Frontend Refactor

**Mục tiêu:** Chuẩn bị API endpoints mới + tách frontend thành file riêng.

### Task 1.1: Split static files

Tách CSS/JS inline từ `index.html` thành file riêng. Giữ no-build setup.

- `kb_agent/dashboard/static/styles.css` — tất cả CSS
- `kb_agent/dashboard/static/app.js` — tất cả JS
- `kb_agent/dashboard/static/index.html` — chỉ HTML structure + `<link>` + `<script>`

Verify dashboard hiện tại vẫn hoạt động y nguyên sau khi tách.

### Task 1.2: Add `/api/overview`

**Endpoint:** `GET /api/overview`

Data sources:

- `manifest.json` → summary, source_repo, created_at
- `GraphStorage.load()` → node/edge counts, languages, modules
- `GraphStorage.load_hotpath()` → top hot symbols
- `GraphStorage.load_features()` → top features
- entries directory → total entry count

Response:

```json
{
  "summary": "Knowledge Base Agent is a tool for...",
  "source_repo": "/path/to/repo",
  "created_at": "2025-01-15T10:30:00",
  "stats": {
    "total_entries": 150,
    "node_count": 89,
    "edge_count": 234
  },
  "languages": ["Python"],
  "top_modules": ["kb_agent.query", "kb_agent.graph", ...],
  "top_features": [
    { "id": "graph", "name": "graph", "member_count": 12 }
  ],
  "top_hot_symbols": [
    { "node_id": "...", "name": "RetrievalEngine.retrieve", "hotness": 0.85, "incoming_calls": 8 }
  ]
}
```

Error khi `.kb/` chưa tạo:

```json
{
  "error": { "code": "missing_kb", "message": "Knowledge base not found. Run analyze first." },
  "summary": null,
  "stats": null,
  ...
}
```

### Task 1.3: Add `/api/features/{feature_id}`

**Endpoint:** `GET /api/features/{feature_id}`

Load features từ `GraphStorage.load_features()`, filter by ID, resolve member nodes.

Response:

```json
{
  "id": "graph",
  "name": "graph",
  "naming_basis": "module_prefix",
  "edge_density": 0.42,
  "members": [
    {
      "node_id": "repo/kb_agent/graph/storage.py::GraphStorage.save",
      "name": "GraphStorage.save",
      "kind": "method",
      "path": "kb_agent/graph/storage.py",
      "line_start": 25,
      "line_end": 45,
      "hotness": 0.71
    }
  ],
  "related_files": [
    "kb_agent/graph/storage.py",
    "kb_agent/graph/builder.py"
  ]
}
```

### File thay đổi

- `kb_agent/dashboard/server.py` — thêm 2 endpoint
- `kb_agent/dashboard/static/styles.css` — mới (tách từ index.html)
- `kb_agent/dashboard/static/app.js` — mới (tách từ index.html)
- `kb_agent/dashboard/static/index.html` — giảm xuống HTML structure only

### Exit Criteria

- [ ] Dashboard hiện tại load và hoạt động đúng sau khi split
- [ ] `/api/overview` trả về JSON với stats, features, hot symbols
- [ ] `/api/overview` trả error khi `.kb/` không tồn tại
- [ ] `/api/features/{id}` trả về feature detail với member nodes
- [ ] `/api/features/{id}` trả 404 cho unknown feature

---

## Phase 2: Overview + Feature Explorer Views

**Mục tiêu:** Learner mở dashboard thấy overview thay vì raw graph. Click vào feature xem chi tiết.

### Task 2.1: Thêm app state và routing

Thêm state object trong `app.js`:

```js
const state = {
  activeView: "overview",   // overview | features | graph
  currentNodeId: null,
  currentFeatureId: null,
  currentFilePath: null,
  chatHistory: []
};
```

Simple hash-based router:

- `#overview` → render overview
- `#features` → render feature list
- `#features/{id}` → render feature detail
- `#graph` → render graph (existing)
- Default: `#overview`

Navigation component: top bar hoặc left sidebar với 3 tabs: Overview, Features, Graph.

### Task 2.2: Build Overview View

Fetch `/api/overview`, render cards:

- Project summary card
- Stats row: entries, nodes, edges, languages
- Top features list (clickable → navigate đến feature)
- Top hot symbols list (clickable → mở symbol detail)
- Primary action buttons:
  - "Start with architecture" → `#graph`
  - "Explore features" → `#features`
  - "Ask about this project" → focus chat (Phase 4)

### Task 2.3: Build Feature Explorer View

**Feature List:**

- Fetch `/api/features`
- Render: feature name, member count, edge density
- Click → navigate đến feature detail

**Feature Detail:**

- Fetch `/api/features/{feature_id}`
- Render: name, naming basis, edge density
- Member symbols table: name, kind, path, hotness
- Related files list
- Click member symbol → set `state.currentNodeId` + mở symbol detail panel

### Task 2.4: Symbol Detail Panel

Sử dụng existing `/api/node/{node_id}`.

Hiển thị:

- Name, kind, language
- File path + line range
- Signature, docstring
- AI summary (if available)
- Incoming/outgoing connections
- Hotness score

Thêm action buttons:

- `Explain` → prepares "Function/class này làm gì?"
- `Trace calls` → prepares "Nó gọi những gì?"
- `Impact` → prepares "Nếu sửa nó thì ảnh hưởng gì?"
- `Open source` → mở source snippet

Buttons chỉ chuẩn bị câu hỏi (chưa gửi chat — Phase 4 sẽ wire).

### File thay đổi

- `kb_agent/dashboard/static/app.js` — thêm state, routing, views
- `kb_agent/dashboard/static/styles.css` — thêm styles cho overview, features, symbol detail
- `kb_agent/dashboard/static/index.html` — cập nhật HTML structure cho layout mới

### Exit Criteria

- [ ] Mở dashboard → thấy Overview (không phải raw graph)
- [ ] Click "Explore features" → thấy danh sách features
- [ ] Click feature → thấy detail + member symbols
- [ ] Click member symbol → thấy symbol detail panel
- [ ] Graph view vẫn hoạt động qua navigation tab
- [ ] Symbol detail có 4 action buttons

---

## Phase 3: Chat Backend

**Mục tiêu:** `/api/chat` hoạt động với deterministic KB context. Hoạt động cả khi không có LLM key.

### Task 3.1: Tạo `chat.py` module

Tạo `kb_agent/dashboard/chat.py` với class `ChatHandler`.

Dependencies (import trực tiếp, không gọi MCP stdio):

```text
kb_agent.mcp_server.tools.KBTools
  → kb_callers, kb_callees, kb_impact, kb_node
kb_agent.query.retrieval.RetrievalEngine
  → retrieve(question)
kb_agent.graph.storage.GraphStorage
  → load()
optional: LLM client khi OPENAI_API_KEY configured
```

### Task 3.2: Intent router (rule-based placeholder)

Parse `context.node_id` + `question` keywords:

| Pattern | Intent | Action |
|---------|--------|--------|
| "ai gọi" / "callers" / "who calls" | callers | `KBTools.kb_callers(symbol)` |
| "gọi gì" / "callees" / "calls what" | callees | `KBTools.kb_callees(symbol)` |
| "ảnh hưởng" / "impact" / "thay đổi" | impact | `KBTools.kb_impact(symbol)` |
| có node + câu hỏi chung | explain | `KBTools.kb_node` + `RetrievalEngine.retrieve` |
| không có node | general | `RetrievalEngine.retrieve` |

Ghi chú: Đây là placeholder. Sẽ thay bằng intent classifier sau khi endpoint ổn định.

### Task 3.3: Add `/api/chat` endpoint

**Endpoint:** `POST /api/chat`

Request:

```json
{
  "question": "Function này làm gì?",
  "context": {
    "active_view": "node",
    "node_id": "repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve",
    "feature_id": null,
    "file_path": "kb_agent/query/retrieval.py"
  },
  "history": []
}
```

Response:

```json
{
  "answer": "RetrievalEngine.retrieve là method chính...",
  "citations": [
    {
      "label": "RetrievalEngine.retrieve",
      "path": "kb_agent/query/retrieval.py",
      "line_start": 31,
      "line_end": 110,
      "node_id": "repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve"
    }
  ],
  "suggested_questions": [
    "Trace flow của function này",
    "Ai gọi function này?"
  ],
  "error": null
}
```

`error` field luôn present. `null` khi success.

Error response:

```json
{
  "answer": "",
  "citations": [],
  "suggested_questions": [],
  "error": {
    "code": "missing_kb",
    "message": ".kb/ not found. Run analyze first."
  }
}
```

### Task 3.4: Deterministic mode (no LLM)

Khi không có `OPENAI_API_KEY`:

- Trả về raw context từ KB tools
- Prefix answer với:
  > "LLM is not configured, so this answer is based on indexed graph context only."
- Citations vẫn được generate từ tool results
- Suggested questions vẫn hoạt động

### Task 3.5: LLM-backed mode

Khi có `OPENAI_API_KEY`:

- Compose prompt từ: question + collected context + UI state info
- Gọi LLM để generate answer
- Parse response để extract answer + map citations
- Nếu LLM fail → fallback về deterministic mode

### Task 3.6: Suggested questions generation

Static suggestions dựa trên context type:

**Overview:**

- "Repo này làm gì?"
- "Tôi nên học module nào trước?"
- "Các flow chính của dự án là gì?"
- "Những phần nào quan trọng nhất?"

**Feature:**

- "Feature này giải quyết vấn đề gì?"
- "Các symbol quan trọng nhất là gì?"
- "Feature này phụ thuộc vào module nào?"

**Symbol:**

- "Function/class này làm gì?"
- "Ai gọi nó?"
- "Nó gọi những gì?"
- "Nếu sửa nó thì ảnh hưởng gì?"
- "Tôi nên đọc file nào tiếp?"

### Task 3.7: Citation generation

Từ KB tool results, extract:

- `label` — symbol name
- `path` — file path
- `line_start` / `line_end` — line range
- `node_id` — full node ID

### File thay đổi

- `kb_agent/dashboard/chat.py` — mới
- `kb_agent/dashboard/server.py` — thêm `POST /api/chat`

### Exit Criteria

- [ ] `/api/chat` trả lời "Ai gọi function X?" với callers list + citations
- [ ] `/api/chat` trả lời "Function này làm gì?" với node context
- [ ] Chat hoạt động mà không cần OPENAI_API_KEY
- [ ] Response luôn có `error` field + `citations` array + `suggested_questions`
- [ ] Suggested questions thay đổi theo `context.active_view`
- [ ] LLM mode trả về answer tốt hơn deterministic khi có API key
- [ ] LLM fail → fallback về deterministic mode

---

## Phase 4: Chat Panel + Frontend Integration

**Mục tiêu:** Chat panel trong UI, learner hỏi trực tiếp, chat biết context hiện tại.

### Task 4.1: Layout update

Cập nhật layout thành 2 cột:

```text
+------------------------------------------------------+----------------------+
| Main Learning View                                   | Chat Companion       |
|                                                      |                      |
| Overview / Feature / Symbol / Source / Graph         | Messages             |
|                                                      | Input box            |
|                                                      | Suggested questions  |
+------------------------------------------------------+----------------------+
```

Chat panel cố định bên phải, main view chiếm phần còn lại.

### Task 4.2: Build Chat Panel

Components:

- **Message list** — user messages (right) + bot messages (left) + citations
- **Input box** — text input + send button
- **Loading state** — spinner khi đang chờ response
- **Error display** — khi API trả về error

Chat history lưu trong `state.chatHistory`.

### Task 4.3: Context tracking

Mỗi chat request gửi current state:

```js
const context = {
  active_view: state.activeView,
  node_id: state.currentNodeId,
  feature_id: state.currentFeatureId,
  file_path: state.currentFilePath
};
```

Update context tự động khi user navigate hoặc click symbol/feature.

### Task 4.4: Suggested questions

- Hiển thị dưới dạng clickable chips/tags
- Update sau mỗi answer (từ response.suggested_questions)
- Default suggestions dựa trên activeView
- Click suggestion → gửi như chat message

### Task 4.5: Wire symbol buttons to chat

Symbol detail panel buttons:

- `Explain` → gửi "Function/class này làm gì?" đến chat
- `Trace calls` → gửi "Nó gọi những gì?"
- `Impact` → gửi "Nếu sửa nó thì ảnh hưởng gì?"
- `Open source` → mở source snippet view

### Task 4.6: Source snippet panel

Sử dụng `/api/file/{path}?start=X&end=Y`.

Hiển thị:

- Plain text với line numbers
- Highlight node line range (light background)
- "Ask about this code" button → gửi chat với file context

### Task 4.7: Citation rendering

Citations trong chat message:

- Hiển thị dạng: `📄 RetrievalEngine.retrieve (line 31-110)`
- Click → navigate đến symbol detail hoặc open source
- Multiple citations hiển thị dạng list

### File thay đổi

- `kb_agent/dashboard/static/app.js` — thêm chat panel, context tracking, suggested questions
- `kb_agent/dashboard/static/styles.css` — thêm chat styles, layout 2 cột
- `kb_agent/dashboard/static/index.html` — thêm chat panel container

### Exit Criteria

- [ ] Chat panel luôn hiển thị bên phải
- [ ] Gõ câu hỏi → nhận answer với citations
- [ ] Click "Explain" trên symbol → chat tự động hỏi về symbol đó
- [ ] Suggested questions thay đổi theo view hiện tại
- [ ] Click suggestion → gửi message
- [ ] Citations hiển thị link đến file/symbol
- [ ] Source snippet hiển thị với line numbers + highlight
- [ ] Chat context update khi navigate view/click symbol

---

## Phase 5: Testing + Polish

**Mục tiêu:** Đảm bảo chất lượng, pass toàn bộ test suite.

### Task 5.1: Backend tests — Overview + Features

Thêm vào `tests/test_dashboard_server.py`:

- `/api/overview` returns all expected fields
- `/api/overview` returns structured error when `.kb/` missing
- `/api/features/{id}` returns feature with member nodes
- `/api/features/{id}` returns 404 for unknown feature

### Task 5.2: Backend tests — Chat

Tạo `tests/test_dashboard_chat.py`:

- `/api/chat` works without LLM (deterministic mode)
- `/api/chat` resolves current node context
- `/api/chat` returns citations with correct fields
- `/api/chat` returns suggested questions
- `/api/chat` returns error for missing KB
- Intent routing: callers pattern → kb_callers
- Intent routing: callees pattern → kb_callees
- Intent routing: impact pattern → kb_impact
- Intent routing: general question → retrieval

### Task 5.3: Run full test suite

```bash
pytest
```

Tất cả existing tests + new tests phải pass.

### Task 5.4: Manual QA

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2
python -m scripts.cli dashboard --kb .kb
```

Verify checklist:

- [ ] Overview loads với data
- [ ] Feature list loads, feature detail loads
- [ ] Click member symbol → symbol detail panel
- [ ] Symbol detail buttons hoạt động
- [ ] Source snippet hiển thị đúng
- [ ] Chat answers without LLM key
- [ ] Chat answers with LLM key (nếu có)
- [ ] Suggested questions thay đổi theo context
- [ ] Citations point to real files/symbols
- [ ] Graph view vẫn hoạt động
- [ ] Navigation giữa views hoạt động

### File thay đổi

- `tests/test_dashboard_server.py` — thêm tests cho overview + features
- `tests/test_dashboard_chat.py` — mới

### Exit Criteria

- [ ] Tất cả existing tests pass
- [ ] Tất cả new tests pass
- [ ] Manual QA checklist hoàn thành
- [ ] MVP hoàn thành theo LEARNING_UI_MVP_PLAN.md completion criteria

---

## MVP Completion Criteria (Tổng)

MVP hoàn thành khi:

- [ ] User mở dashboard → thấy Overview (không phải raw graph)
- [ ] User explore được feature
- [ ] User inspect được symbol và source
- [ ] User hỏi chatbot contextual questions
- [ ] Answers có citations
- [ ] App hoạt động mà không cần LLM key
- [ ] Existing test suite pass
