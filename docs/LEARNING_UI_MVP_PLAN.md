# Learning UI + Chatbot MVP Plan

> **Goal:** Build the smallest useful learning experience on top of the existing dashboard.
> The MVP should help a learner open the UI, understand the project, inspect a feature or symbol, and ask contextual follow-up questions through a chatbot.

## 1. MVP Scope

The MVP should focus on learning flow, not visual polish.

Ship these five pieces:

- Learning overview
- Feature explorer
- Symbol/source detail
- Chat companion
- Suggested questions

Do not build these yet:

- Full guided tour engine
- Persona-adaptive UI
- Full diff visualization
- Notes/bookmarks
- Multi-user accounts
- Frontend framework migration

## 2. User Journey

Target first-time learner journey:

```text
Open dashboard
  -> see project overview
  -> choose a feature
  -> inspect key symbols/files
  -> ask chatbot follow-up questions
  -> get cited answers and suggested next questions
```

The MVP is successful if the learner does not need to start from a raw graph.

## 3. MVP UI

### 3.1 Layout

```text
+------------------------------------------------------+----------------------+
| Main Learning View                                   | Chat Companion       |
|                                                      |                      |
| Overview / Feature / Symbol / Source / Graph         | Ask about this...    |
|                                                      | Suggested questions  |
+------------------------------------------------------+----------------------+
```

### 3.2 Navigation

Add a simple left or top navigation:

- `Overview`
- `Features`
- `Graph`

The symbol/source detail can open as a panel from any view.

### 3.3 Overview View

Show:

- Project summary
- Total entries
- Node/edge counts
- Languages
- Main modules
- Top hot symbols
- Top features
- KB generated time

Primary actions:

- "Start with architecture"
- "Explore features"
- "Ask about this project"

### 3.4 Feature Explorer

Use existing feature data from `/api/features`.

Show:

- Feature list
- Feature detail
- Member symbols
- Related files
- Hot members

When user clicks a member symbol:

- Open symbol detail
- Set chat context to that symbol

### 3.5 Symbol Detail

Use existing `/api/node/{node_id}`.

Show:

- Name
- Kind
- Language
- File path and line range
- Signature
- Docstring
- AI summary if available
- Incoming/outgoing connections
- Hotness

Add buttons:

- `Explain`
- `Trace calls`
- `Impact`
- `Open source`

Each button sends a prepared question to the chat panel.

### 3.6 Source Snippet

Use existing `/api/file/{file_path}`.

MVP source reader can be simple:

- Plain text
- Line numbers
- Highlight approximate node line range

Syntax highlighting can wait.

## 4. MVP Chat Companion

### 4.1 Chat Panel Behavior

Chat panel is always visible on the right.

It should know current context:

- Current view
- Current feature
- Current node
- Current file
- Selected source range if available later

### 4.2 Suggested Questions

Default suggestions on overview:

- "Repo này làm gì?"
- "Tôi nên học module nào trước?"
- "Các flow chính của dự án là gì?"
- "Những phần nào quan trọng nhất?"

Suggestions on feature:

- "Feature này giải quyết vấn đề gì?"
- "Các symbol quan trọng nhất là gì?"
- "Feature này phụ thuộc vào module nào?"

Suggestions on symbol:

- "Function/class này làm gì?"
- "Ai gọi nó?"
- "Nó gọi những gì?"
- "Nếu sửa nó thì ảnh hưởng gì?"
- "Tôi nên đọc file nào tiếp?"

### 4.3 Backend Endpoint

Add:

```text
POST /api/chat
```

Request shape:

```json
{
  "question": "Function này làm gì?",
  "context": {
    "active_view": "node",
    "node_id": "repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve(question: str)",
    "feature_id": null,
    "file_path": "kb_agent/query/retrieval.py"
  },
  "history": []
}
```

Response shape:

```json
{
  "answer": "...",
  "citations": [
    {
      "label": "RetrievalEngine.retrieve",
      "path": "kb_agent/query/retrieval.py",
      "line_start": 31,
      "line_end": 110,
      "node_id": "..."
    }
  ],
  "error": null,
  "suggested_questions": [
    "Trace flow của function này",
    "Ai gọi function này?",
    "Nếu sửa function này thì ảnh hưởng gì?"
  ]
}
```

The response should always include an `error` field. Use `null` on success.

Error response shape:

```json
{
  "answer": "",
  "citations": [],
  "suggested_questions": [],
  "error": {
    "code": "missing_kb",
    "message": ".kb/manifest.json was not found. Run analyze first."
  }
}
```

### 4.4 Chat Implementation

MVP can use a simple rule-based router as a placeholder. Replace it with an intent classifier after the endpoint behavior is stable.

```text
if current node exists and question asks "ai gọi":
  KBTools.kb_callers
elif current node exists and question asks "gọi gì":
  KBTools.kb_callees
elif current node exists and question asks "ảnh hưởng":
  KBTools.kb_impact
elif current node exists:
  KBTools.kb_node + RetrievalEngine.retrieve
else:
  RetrievalEngine.retrieve
```

Implementation dependency:

```text
kb_agent/dashboard/chat.py
  -> kb_agent.mcp_server.tools.KBTools
  -> kb_agent.query.retrieval.RetrievalEngine
  -> kb_agent.graph.storage.GraphStorage
  -> optional kb_agent.analyzer.llm.LLMClient
```

Do not call the MCP server over stdio from dashboard chat. Import and use the underlying Python classes directly.

Then compose an LLM prompt if `OPENAI_API_KEY` is configured.

If no LLM key exists, return deterministic context from KB tools with a clear message:

```text
LLM is not configured, so this answer is based on indexed graph context only.
```

## 5. Backend Tasks

### Task 1: Add Overview API

Add:

```text
GET /api/overview
```

Data sources:

- `manifest.json`
- `GraphStorage.load()`
- `GraphStorage.load_hotpath()`
- `GraphStorage.load_features()`
- entries directory

Return:

- summary entry if available
- counts
- languages
- top modules
- top features
- top hot symbols
- created_at

If `.kb/manifest.json` is missing, return a structured error and show an "analyze first" empty state in the UI.

### Task 2: Add Chat API

Add:

```text
POST /api/chat
```

Create a small module:

```text
kb_agent/dashboard/chat.py
```

Responsibilities:

- Parse chat request
- Resolve UI context
- Route to graph/retrieval helpers
- Compose answer
- Produce citations
- Produce suggested questions

### Task 3: Improve Feature API

Current `/api/features` returns feature list. MVP should add:

```text
GET /api/features/{feature_id}
```

Return:

- feature metadata
- member node details
- related files
- hotness per member

### Task 4: Source Snippet Helper

Reuse `/api/file/{file_path}`.

Optionally add query params:

```text
?start=10&end=40
```

The current endpoint already supports `start` and `end`.

## 6. Frontend Tasks

### Task 1: Split Static Files

Move inline CSS/JS out of:

```text
kb_agent/dashboard/static/index.html
```

Into:

```text
kb_agent/dashboard/static/styles.css
kb_agent/dashboard/static/app.js
```

Keep no-build setup.

### Task 2: Add App State

Track:

```js
state = {
  activeView: "overview",
  currentNodeId: null,
  currentFeatureId: null,
  currentFilePath: null,
  chatHistory: []
}
```

### Task 3: Build Overview View

Render `/api/overview`.

Cards/sections:

- Project summary
- Stats
- Top features
- Hot symbols
- Suggested questions

### Task 4: Build Feature View

Render feature list and feature detail.

Clicking a symbol sets:

```js
state.currentNodeId = node.id
state.activeView = "node"
```

### Task 5: Build Chat Panel

Components:

- Messages
- Input box
- Send button
- Suggested questions
- Loading state

Every request sends the current state as context.

### Task 6: Connect Symbol Buttons to Chat

In symbol detail:

- Explain
- Trace calls
- Impact

These should prefill/send chat questions.

## 7. MVP File Changes

Expected files to change or add:

```text
kb_agent/dashboard/server.py
kb_agent/dashboard/chat.py
kb_agent/dashboard/static/index.html
kb_agent/dashboard/static/styles.css
kb_agent/dashboard/static/app.js
tests/test_dashboard_server.py
tests/test_dashboard_chat.py
docs/LEARNING_UI_MVP_PLAN.md
```

## 8. Testing Plan

### Backend Tests

Add tests for:

- `/api/overview` returns counts and features
- `/api/features/{feature_id}` returns member nodes
- `/api/chat` works without LLM
- `/api/chat` resolves current node context
- `/api/chat` returns citations
- `/api/chat` returns suggested questions
- path traversal remains blocked for source files

### Manual Test

Run:

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2
python -m scripts.cli dashboard --kb .kb
```

Then verify:

- Overview loads
- Feature list loads
- Clicking symbol opens detail
- Chat answers "Function này làm gì?"
- Chat answers "Ai gọi nó?"
- Chat answers "Nếu sửa nó thì ảnh hưởng gì?"
- Citations point to real files/symbols

## 9. MVP Completion Criteria

MVP is complete when:

- User can start from overview instead of raw graph.
- User can explore a feature.
- User can inspect a symbol and source.
- User can ask contextual follow-up questions.
- Answers include citations.
- App still works without LLM key using deterministic graph context.
- Existing test suite passes.

## 10. Suggested Implementation Order

1. Add `/api/overview`
2. Add deterministic `/api/chat`
3. Add LLM-backed chat answer composition
4. Split frontend files
5. Build overview view
6. Build feature explorer
7. Add chat panel
8. Wire symbol detail actions to chat
9. Add backend tests
10. Run full test suite
