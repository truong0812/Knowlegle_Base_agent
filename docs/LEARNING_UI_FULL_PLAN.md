# Learning UI + Chatbot Full Development Plan

> **Goal:** Build a learning-oriented codebase exploration experience on top of Knowledge Base Agent.
> The UI should help new developers understand a repository through guided paths, feature/domain views, flow tracing, source reading, graph context, and an embedded chatbot that can answer follow-up questions with citations.

## 1. Product Vision

The current dashboard is a technical graph viewer. The next product step is to turn it into a learning workspace.

The learning UI should answer:

- What should I learn first?
- Which modules/features matter most?
- How does a flow move through the codebase?
- What does this symbol do, and why does it matter?
- What changes between versions?
- What should I ask or inspect next?

The chatbot should not be a generic assistant. It should be context-aware: it knows the current node, feature, source file, flow, tour step, or selected text the learner is viewing.

```text
Learning UI
  -> current context
  -> graph-aware retrieval
  -> source citations
  -> chatbot follow-up
  -> suggested next learning step
```

## 2. Target Experience

### Primary Layout

```text
+------------------------------------------------------+----------------------+
| Learning Workspace                                   | Chat Companion       |
|                                                      |                      |
| Overview / Learning Path / Feature / Flow / Source   | Ask about current    |
| Graph / Diff                                         | context...           |
|                                                      | Suggested questions  |
+------------------------------------------------------+----------------------+
```

The left side is for exploration. The right side is for questions, explanations, and next-step guidance.

### Core Navigation

- `Overview`
- `Learning Paths`
- `Feature Explorer`
- `Flow Explorer`
- `Source Reader`
- `Graph Explorer`
- `Diff / Impact`
- `Chat`

## 3. Learning Surfaces

### 3.1 Overview

The overview is the first screen. It should avoid showing a huge graph immediately.

Content:

- Project summary from `arch.root`
- Language distribution
- Entry points
- Main modules
- Important features
- Hot-path symbols
- Current KB freshness status
- Suggested learning paths

Expected user outcome:

- Learner understands what the repository is.
- Learner knows where to begin.

### 3.2 Learning Paths

Learning paths are curated guided sequences generated from existing KB entries and graph relationships.

Initial paths should be intentionally small. Start with 2-3 manually curated paths, then add generated paths after the path model is proven.

- Architecture overview
- Query and retrieval pipeline
- Symbol graph construction

Each step should include:

- Title
- Short explanation
- Related files
- Related symbols
- Source snippet
- Graph neighborhood
- Suggested question
- Completion state

Path source:

- MVP/full-plan first iteration: manually curated paths stored in code or JSON.
- Later iteration: generate candidate paths from graph data, then allow manual edits.

Generation logic should use:

- `arch.root` and module entries for architecture paths
- hot-path scores for important symbols
- `CALLS` edges for flow-like paths
- feature membership for domain/feature paths
- source file locality to keep paths readable

### 3.3 Feature Explorer

Use existing `feature` entries and `GraphStorage.load_features()`.

Each feature page should show:

- Feature name
- What this feature does
- Member symbols
- Key files
- Main flows
- Dependencies
- Used by
- Hot nodes
- Related learning paths

This is more learner-friendly than starting from raw graph nodes.

### 3.4 Flow Explorer

The flow explorer renders a process as a readable chain, not only as a force graph.

Example:

```text
scripts.cli query
  -> QueryEngine.query
  -> FAISS search
  -> entry loading
  -> result formatting
```

Graph-aware example:

```text
RetrievalEngine.retrieve
  -> detect_intent
  -> QueryEngine.query
  -> build_entry_to_node_mapper
  -> expand_from_seeds
  -> compose_context
```

Flow UI should support:

- Search/select entry point
- Vertical step timeline
- Related call graph
- Source snippet per step
- "Ask about this step"
- "Show impact from here"

### 3.4.1 Flow API Contract

Add:

```text
GET /api/flow?symbol=...&depth=4
```

Response:

```json
{
  "entry_symbol": {
    "id": "...",
    "name": "RetrievalEngine.retrieve",
    "path": "kb_agent/query/retrieval.py",
    "line_start": 31,
    "line_end": 110
  },
  "steps": [
    {
      "order": 1,
      "node_id": "...",
      "name": "RetrievalEngine.retrieve",
      "kind": "method",
      "path": "kb_agent/query/retrieval.py",
      "line_start": 31,
      "line_end": 110,
      "summary": "...",
      "edge_from_previous": null,
      "confidence": 1.0,
      "hotness": 0.71
    }
  ],
  "edges": [
    {
      "source": "...",
      "target": "...",
      "kind": "calls",
      "confidence": 0.85
    }
  ],
  "truncated": false,
  "warnings": []
}
```

Implementation notes:

- Resolve `symbol` with exact node id first, then name/fuzzy match.
- Prefer call-chain traversal over full graph expansion.
- Cap result size for UI readability.
- Return `warnings` when the symbol is ambiguous, missing, or traversal is truncated.

### 3.5 Source Reader

The source reader should be integrated into the learning UI, not hidden behind raw API output.

Capabilities:

- Syntax-highlighted source
- Line numbers
- Highlight selected symbol range
- Side panel with node metadata
- Callers/callees
- Related features
- Ask about selected text

### 3.6 Graph Explorer

Keep the existing D3 graph, but reposition it as an advanced exploration tool.

Improve it with:

- Layout modes: feature, module, call graph, dependency graph
- Node clustering by feature/module
- Edge type toggles
- Confidence and hotness visual encoding
- Search result focus
- Click-through to source and chat

### 3.7 Diff / Impact

Use the existing temporal graph and diff machinery.

UI capabilities:

- Select version A and version B
- Show added/removed/modified nodes
- Show added/removed edges
- Explain impact of changes
- Link changed symbols to source
- Ask chatbot to explain a change

## 4. Chat Companion

### 4.1 Role

The chatbot is a learning companion attached to the current exploration context.

It should answer:

- "Explain this function."
- "Why does this module exist?"
- "Who calls this?"
- "What does this call?"
- "What happens if I change this?"
- "Trace this flow."
- "What should I learn next?"
- "Compare these versions."

### 4.2 Context Contract

Frontend sends the current UI context with each chat request.

```json
{
  "question": "Why does this function matter?",
  "context": {
    "active_view": "node",
    "node_id": "repo/kb_agent/query/retrieval.py::RetrievalEngine.retrieve(question: str)",
    "feature_id": null,
    "file_path": "kb_agent/query/retrieval.py",
    "selected_text": null,
    "tour_id": null,
    "tour_step": null
  }
}
```

### 4.3 Backend Endpoint

Add:

```text
POST /api/chat
```

Request:

- `question`
- `context`
- optional `history`
- optional `mode`: `beginner`, `maintainer`, `agent`

Response:

- `answer`
- `citations`
- `related_symbols`
- `suggested_questions`
- `suggested_next_steps`
- optional `used_tools`
- optional `error`

### 4.4 Chat Orchestration

Backend should route questions through existing engines:

```text
question + UI context
  -> classify chat intent
  -> collect local context
  -> retrieve graph-aware context if needed
  -> compose LLM prompt
  -> answer with citations
```

Intent types:

- `explain`
- `trace`
- `relationship`
- `impact`
- `compare`
- `guide`
- `general`

Internal capabilities:

- `kb_agent.mcp_server.tools.KBTools` as a convenience wrapper for node, callers, callees, impact, and explore behavior
- `kb_agent.query.retrieval.RetrievalEngine` for graph-aware context
- `kb_agent.query.engine.QueryEngine` for semantic seed search
- `kb_agent.graph.storage.GraphStorage` for direct graph access
- `kb_agent.graph.temporal.TemporalGraphManager` or `kb_agent.query.temporal_query.TemporalQueryHandler` for version diffs

The chatbot does not need to call the MCP server internally. It can directly call the Python classes that power the MCP tools.

Dependency direction:

```text
dashboard/chat.py
  -> KBTools
  -> RetrievalEngine / QueryEngine
  -> GraphStorage / TemporalQueryHandler
  -> optional LLMClient
```

Do not route dashboard chat through stdio MCP. MCP remains an external integration surface for other agents.

### 4.5 Streaming

MVP can return a synchronous JSON response. The full implementation should add streaming for LLM-backed answers.

Recommended endpoint:

```text
POST /api/chat/stream
```

Transport:

- Server-Sent Events via FastAPI `StreamingResponse`
- Emit events for `status`, `token`, `citation`, `suggested_questions`, and `done`

This keeps the normal `/api/chat` endpoint simple while allowing the UI to feel responsive for longer explanations.

### 4.6 Answer Format

Every answer should be grounded.

Recommended format:

```text
Answer
Why it matters
Related files/symbols
Suggested next questions
Sources
```

Rules:

- Avoid generic answers.
- Cite files/symbols where possible.
- If context is missing, say what needs to be indexed.
- Keep explanations short by default, with follow-up suggestions.

## 5. Learning Modes

Add a simple mode switch.

### Beginner

- More explanation
- Less jargon
- More "why this matters"
- Suggested next steps

### Maintainer

- Dependency and impact focused
- Hot paths
- Risk and ownership
- Version diff

### Agent

- Context packs
- Retrieval output
- MCP tool references
- Concise technical summaries

## 6. Personal Learning State

Do not persist learning state under `.kb/`. The `.kb/` directory is generated output and may be deleted during rebuilds.

Use one of these storage locations:

- Browser `localStorage` for MVP
- `.learning/` at repo root for local server-side persistence
- A user-selected app data directory for future multi-repo usage

Recommended server-side path:

Possible files:

```text
.learning/
  progress.json
  notes.jsonl
  chat_sessions.jsonl
  bookmarks.json
```

Track:

- Completed tour steps
- Viewed features
- Viewed symbols
- Bookmarked files
- Asked questions
- Notes

This should be optional and local-only.

## 7. Backend API Plan

Add these endpoints:

```text
GET  /api/overview
GET  /api/learning-paths
GET  /api/learning-paths/{path_id}
GET  /api/features
GET  /api/features/{feature_id}
GET  /api/flow?symbol=...
GET  /api/source/{file_path}
GET  /api/impact?symbol=...
GET  /api/diff?from=...&to=...
POST /api/chat
GET  /api/learning/progress
POST /api/learning/progress
POST /api/learning/bookmark
POST /api/learning/note
```

Reuse existing endpoints where possible:

- `/api/status`
- `/api/nodes`
- `/api/edges`
- `/api/search`
- `/api/node/{id}`
- `/api/hotpath`
- `/api/features`
- `/api/file/{path}`
- `/api/versions`

## 8. Frontend Architecture

The current `index.html` is enough for the existing dashboard, but the learning UI should be split into maintainable modules.

Use a transition plan instead of splitting into many files immediately.

MVP/no-build structure:

```text
kb_agent/dashboard/static/
  index.html
  styles.css
  api.js
  views.js
  chat.js
  app.js
```

Conventions:

- `api.js` exports typed fetch helpers.
- `views.js` exports `renderOverview`, `renderFeatures`, `renderNodeDetail`, and `renderGraph`.
- `chat.js` owns chat state, rendering, and calls to `/api/chat`.
- `app.js` owns global state and routing.

Every view renderer should follow:

```js
export async function render(container, state, api) {
  // fetch data, render DOM, bind events
}
```

Later structure, only after views become too large:

```text
kb_agent/dashboard/static/
  index.html
  styles.css
  app.js
  api.js
  state.js
  views/
    overview.js
    learning_paths.js
    feature_explorer.js
    flow_explorer.js
    source_reader.js
    graph_explorer.js
    diff_view.js
    chat_panel.js
```

Alternative later: move to React/Vite if frontend complexity keeps growing.

For the first iteration, plain JavaScript modules are acceptable and avoid a build step.

## 9. Implementation Phases

### Phase A1: Overview Foundation

- Add `/api/overview`
- Add learning home view
- Refactor current dashboard JS/CSS out of `index.html`
- Verify `.kb/manifest.json` exists and expose KB freshness in overview

Exit criteria:

- Learner can open dashboard and understand project structure without starting from graph.

### Phase A2: Feature and Source Foundation

- Add feature explorer detail view
- Add source reader panel

Exit criteria:

- Learner can inspect a feature, open a symbol, and read its source context.

### Phase B: Chat Companion MVP

- Add `/api/chat`
- Implement chat intent classification
- Use current UI context in chat requests
- Use direct Python classes for node/callers/callees/impact/retrieval
- Return citations and suggested questions
- Add persistent chat panel

Exit criteria:

- Learner can click a symbol and ask follow-up questions grounded in that symbol.

### Phase C: Guided Learning Paths

- Add learning path model
- Start with 2-3 manually curated built-in paths
- Document and prototype graph-based path generation
- Add step-by-step UI
- Track completion in `localStorage` or `.learning/progress.json`

Exit criteria:

- Learner can follow an end-to-end path through a major subsystem.

### Phase D: Flow Explorer

- Add `/api/flow`
- Build call chain/timeline renderer
- Link flow steps to source and chat
- Support "trace from current symbol"

Exit criteria:

- Learner can understand a process as a readable sequence.

### Phase E: Diff / Impact Learning

- Add `/api/diff`
- Add version comparison UI
- Add impact explanation from changed nodes
- Integrate diff with chatbot

Exit criteria:

- Learner can understand what changed between two snapshots and why it matters.

### Phase F: Polish and Learning Memory

- Add bookmarks and notes
- Improve responsive layout
- Add beginner/maintainer/agent modes
- Add richer suggested questions
- Add onboarding empty states

Exit criteria:

- UI feels like a learning product, not only a graph debugger.

## 10. Testing Strategy

Backend tests:

- Overview API
- Feature detail API
- Flow API
- Chat intent routing
- Chat context collection
- Citation formatting
- Diff API
- Learning progress persistence
- Path traversal protection for source reading

Frontend smoke tests:

- Dashboard loads
- Overview renders
- Node click opens detail
- Chat sends current context
- Search highlights results
- Flow view renders chain

Manual QA:

- Rebuild `.kb`
- Launch dashboard
- Complete one learning path
- Ask chatbot about a clicked node
- Trace a flow
- Compare two versions

## 11. Risks

### LLM Hallucination

Mitigation:

- Always retrieve context first.
- Require citations.
- Answer "not enough indexed context" when missing.

### UI Complexity

Mitigation:

- Keep graph as one view, not the main product shell.
- Build learning views incrementally.
- Avoid adding a frontend build step until needed.

### KB Staleness

Mitigation:

- Show KB `created_at` and source repo.
- Add "KB may be stale" warning when source files are newer than manifest.
- Encourage rebuild from UI later.

### Performance

Mitigation:

- Cap graph render size.
- Use focused subgraphs by default.
- Load source and details lazily.

## 12. Success Criteria

The full learning UI is successful when a new developer can:

- Understand the project purpose in under 5 minutes.
- Follow a guided path through a core subsystem.
- Ask contextual questions without copying file paths manually.
- Jump from explanation to source.
- Understand relationships and impact.
- Use graph view only when they need deeper exploration.
