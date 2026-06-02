# AI Learning Platform Full Plan

> Goal: evolve Knowledge Base Agent from a graph-oriented code exploration tool into a complete AI learning platform.
> The platform should help learners understand a repository through natural-language tutoring, guided learning paths, topic pages, progress tracking, recommendations, and graph-backed citations.

## Current Status

Updated: 2026-06-02

Phase 1, Phase 2, and Phase 3 are complete.

Completed:

- `kb_agent.learning` package created.
- Learning API contract models created.
- Citation and progress event models created.
- Prompt template folder created with `v1` templates.
- Dashboard server exposes `/api/learning/*` Phase 1 endpoints.
- Lightweight progress persists to `.kb/learning/progress.json`.
- Progress events append to `.kb/learning/events.jsonl`.
- `LearningApi` supports injected read-only graph storage.
- Graph, manifest, status, feature, and progress reads are cached per `LearningApi` instance.
- Phase 1 contract tests added.
- `kb_agent.learning.tutor` natural-language tutor module created.
- Tutor context builder selects relevant graph nodes and supporting relationships.
- Tutor responses attach citations when graph context is available.
- Tutor responses include suggested questions, related topics, and next steps.
- Tutor prompt is loaded from `kb_agent/learning/prompts/tutor_answer.v1.txt` and includes serialized graph context.
- Deterministic no-LLM fallback returns structured learner-friendly answers.
- `/api/learning/tutor/chat?stream=true` returns Server-Sent Events.
- Phase 2 tutor behavior and streaming tests added.
- `kb_agent.learning.explainer` topic explainer module created.
- Topic pages now include learner-friendly explanations, why-it-matters text, examples, citations, prerequisites, related topics, and graph neighborhood context.
- Topic search now scores title, path, type, signature, and aliases.
- Topic page responses are cached in `.kb/learning/topics.json`.
- Dashboard UI includes a Topics route with search, topic cards, citation cards, related topic links, graph neighborhood, and ask-about-topic actions.
- Phase 3 topic explainer, search, cache, and degradation tests added.

Verification:

- `pytest -q` -> `386 passed, 3 warnings`
- `ruff check kb_agent\learning\api.py kb_agent\learning\tutor.py kb_agent\dashboard\server.py tests\test_learning_platform_phase1.py` -> passed
- `ruff check kb_agent\learning\api.py kb_agent\learning\explainer.py tests\test_learning_platform_phase3.py` -> passed
- `node --check kb_agent\dashboard\static\app.js` -> passed

Next phase:

- Phase 4: Learning Paths.

## 1. Product Vision

The current dashboard exposes the knowledge graph too directly. A complete product should make the graph an intelligence layer, not the primary user experience.

The user-facing product should answer:

- What should I learn first?
- What do I need to understand this topic?
- Can you explain this in simple language?
- Can you show an example from the source code?
- What should I study next?
- Where did I leave off?

The knowledge graph remains central, but it should power:

- learning path generation
- prerequisite detection
- related concept discovery
- impact and dependency explanation
- source-grounded citations
- personalized recommendations
- lightweight learning progress

## 2. Target Users

The initial version targets a single local user. Multi-user support is out of scope.

### 2.1 New Developer

Needs a fast, guided path into an unfamiliar codebase.

Primary jobs:

- understand architecture
- learn major modules
- inspect important flows
- ask follow-up questions
- connect source files to product behavior

### 2.2 Maintainer

Needs to explain and curate repository knowledge efficiently.

Primary jobs:

- identify key concepts and hot paths
- review generated learning paths
- verify citations
- detect stale knowledge
- improve documentation coverage

### 2.3 AI Coding Agent

Needs structured context for code assistance.

Primary jobs:

- retrieve relevant graph context
- understand dependencies before changing code
- trace impact
- explain implementation choices
- produce source-cited answers

## 3. Product Principles

- Natural language first: users should not need to understand raw nodes and relationships.
- Graph as engine: graph views are useful, but secondary.
- Source-grounded: every important answer should include citations or related source references.
- Guided by default: the platform should suggest next steps instead of leaving the learner in an empty explorer.
- Progressive disclosure: show simple explanations first, then allow deeper graph, source, and flow inspection.
- Lightweight progress: track viewed topics, completed lessons, active goals, and last context.
- Accessible: keyboard-friendly navigation, readable contrast, and semantic HTML by default.
- Human-editable: generated paths and topic summaries should be easy to override later.

## 4. Core Experience

### 4.1 Learning Dashboard

The dashboard is the first screen.

It should show:

- project summary
- current knowledge base status
- recommended starting paths
- learning progress
- important modules/features
- recent activity
- suggested next action

Primary actions:

- Start recommended path
- Continue active path
- Ask the AI tutor
- Explore a topic
- Open graph explorer

### 4.2 Learning Path

A learning path is an ordered sequence of lessons generated from graph structure and repository knowledge.

Each path should contain:

- title
- audience level
- estimated time
- learning objectives
- ordered lessons
- prerequisites
- completion state

Initial paths:

- Architecture overview
- Query and retrieval pipeline
- Knowledge graph construction
- Dashboard and API flow
- Analyzer pipeline

Each lesson should contain:

- explanation
- key concepts
- source references
- related symbols
- examples
- suggested follow-up questions
- next lesson recommendation

### 4.3 Topic Page

A topic page turns a graph node, feature, module, or source file into a learner-friendly page.

It should show:

- plain-language explanation
- why it matters
- prerequisites
- related topics
- source snippets
- examples
- citations
- learner progress
- ask-about-this-topic action

Topic types:

- concept
- feature
- module
- source file
- function/method/class
- flow
- external dependency

### 4.4 AI Tutor Chat

The AI tutor should behave like a context-aware teacher, not a raw retrieval endpoint.

It should support:

- natural-language answers
- simpler explanation on request
- examples from source code
- citations
- follow-up questions
- current-page awareness
- learning path recommendation
- related topic discovery

The tutor should avoid:

- returning raw nodes and edges as the main answer
- exposing internal graph jargon unless asked
- claiming certainty without enough context
- answering without citations when source grounding is available

### 4.5 Progress And Memory

The platform should remember what the learner has done with a small single-user progress model.

Track:

- completed lessons
- viewed topics
- preferred explanation level
- active learning goal
- last visited context

Memory should influence:

- recommended next steps
- tutor answer depth
- path ordering
- continue-from-last-session behavior

### 4.6 Recommendation Engine

Recommendations should combine graph structure and learner state.

Signals:

- prerequisites
- hot-path scores
- feature importance
- incomplete paths
- recently viewed topics
- graph centrality

Recommendation examples:

- Learn this prerequisite first.
- Continue this path from lesson 3.
- Explore this flow because it connects two topics you studied.
- Open this module because it is central to the current path.

### 4.7 Knowledge Explorer

The graph explorer remains available, but it is not the default experience.

It should support:

- graph visualization
- readable relationship labels
- node detail panel
- filters by type
- search
- neighborhood expansion
- ask-about-node action

Relationship labels should be learner-friendly:

- calls
- depends on
- belongs to
- implements
- uses
- extends
- related to
- prerequisite for

## 5. Platform Architecture

```text
+-----------------------+
| Knowledge Sources    |
+----------+------------+
           |
           v
+-----------------------+
| Ingestion Pipeline    |
+----------+------------+
           |
           v
+-----------------------+       +-----------------------+
| Knowledge Graph       |<----->| Vector Index          |
+----------+------------+       +----------+------------+
           |                               |
           v                               v
+-------------------------------------------------------+
| Retrieval And Context Builder                         |
+----------------------+--------------------------------+
                       |
                       v
+-------------------------------------------------------+
| Learning Intelligence Layer                           |
| - Answer Synthesizer                                  |
| - Learning Planner                                    |
| - Topic Explainer                                     |
| - Recommendation Engine                               |
| - Citation Resolver                                   |
+----------------------+--------------------------------+
                       |
                       v
+-------------------------------------------------------+
| User State Layer                                      |
| - Progress                                            |
| - Preferences                                         |
| - Memory                                              |
+----------------------+--------------------------------+
                       |
                       v
+-------------------------------------------------------+
| Learning UI                                           |
| Dashboard | Paths | Topic | Tutor | Graph             |
+-------------------------------------------------------+
```

## 6. Backend Modules

### 6.1 `learning/models.py`

Defines platform data models:

- `LearningPath`
- `LearningLesson`
- `TopicPage`
- `TutorResponse`
- `UserProgress`
- `Recommendation`
- `Citation`
- `LearningContext`

### 6.2 `learning/planner.py`

Builds learning paths from graph data.

Responsibilities:

- select important topics
- detect prerequisites
- order lessons
- produce path metadata
- handle circular dependencies gracefully

### 6.3 `learning/explainer.py`

Turns graph entries into natural-language topic pages.

Responsibilities:

- summarize topic
- explain why it matters
- generate examples
- attach citations
- identify prerequisites and related topics
- provide fallback summaries when LLM is unavailable

### 6.4 `learning/tutor.py`

Synthesizes natural-language chatbot answers.

Responsibilities:

- classify user intent
- retrieve context
- compose answer
- attach citations
- produce suggested follow-ups
- return related topics
- support streaming responses when configured

### 6.5 `learning/progress.py`

Stores and updates learner state.

Responsibilities:

- mark lessons complete
- record topic views
- store preferred explanation level
- store active learning goal
- store last visited context
- compute progress summary

### 6.6 `learning/recommendations.py`

Computes next actions.

Responsibilities:

- recommend paths
- recommend topics
- recommend continuation actions
- rank results by graph and progress signals

### 6.7 `learning/citations.py`

Normalizes citations across entries, graph nodes, and source files.

Responsibilities:

- resolve source paths
- attach line ranges
- attach entry ids
- deduplicate citations
- validate citation availability

## 7. API Contract

All endpoints should return user-facing content first and graph context only as supporting data.

### 7.1 Dashboard

```text
GET /api/learning/dashboard
```

Response:

```json
{
  "summary": {
    "project_name": "Knowledge Base Agent",
    "description": "...",
    "source_repo": "...",
    "created_at": "2026-06-02T00:00:00"
  },
  "kb_status": {
    "available": true,
    "node_count": 0,
    "edge_count": 0,
    "entry_count": 0,
    "warnings": []
  },
  "progress": {
    "completed_lessons": 0,
    "viewed_topics": 0,
    "active_path_id": null,
    "last_context": null
  },
  "recommended_paths": [],
  "recommended_topics": [],
  "important_features": [],
  "recent_activity": [],
  "suggested_next_action": {
    "type": "start_path",
    "label": "Start with architecture",
    "target_id": "architecture-overview"
  }
}
```

### 7.2 Learning Paths

```text
GET /api/learning/paths
```

Response:

```json
{
  "paths": [
    {
      "id": "architecture-overview",
      "title": "Architecture overview",
      "description": "...",
      "audience_level": "beginner",
      "estimated_minutes": 20,
      "lesson_count": 5,
      "completed_lesson_count": 0,
      "prerequisites": [],
      "status": "not_started"
    }
  ]
}
```

```text
GET /api/learning/paths/{path_id}
```

Response:

```json
{
  "id": "architecture-overview",
  "title": "Architecture overview",
  "description": "...",
  "audience_level": "beginner",
  "estimated_minutes": 20,
  "objectives": [],
  "prerequisites": [],
  "lessons": [
    {
      "id": "lesson-1",
      "title": "Repository shape",
      "summary": "...",
      "explanation": "...",
      "key_concepts": [],
      "related_topics": [],
      "citations": [],
      "completed": false,
      "next_lesson_id": "lesson-2"
    }
  ],
  "progress": {
    "completed_lesson_count": 0,
    "lesson_count": 5,
    "status": "not_started"
  }
}
```

```text
POST /api/learning/paths/{path_id}/lessons/{lesson_id}/complete
```

Response:

```json
{
  "path_id": "architecture-overview",
  "lesson_id": "lesson-1",
  "completed": true,
  "progress": {
    "completed_lesson_count": 1,
    "lesson_count": 5,
    "status": "in_progress"
  },
  "next_action": {
    "type": "continue_lesson",
    "target_id": "lesson-2",
    "label": "Continue to lesson 2"
  }
}
```

### 7.3 Topic Pages

```text
GET /api/learning/topics/{topic_id}
```

Response:

```json
{
  "id": "topic-id",
  "type": "module",
  "title": "...",
  "summary": "...",
  "explanation": "...",
  "why_it_matters": "...",
  "examples": [],
  "prerequisites": [],
  "related_topics": [],
  "related_symbols": [],
  "citations": [],
  "progress": {
    "viewed": true,
    "last_viewed_at": "2026-06-02T00:00:00"
  },
  "suggested_questions": [],
  "graph_context": {
    "nodes": [],
    "relationships": []
  },
  "warnings": []
}
```

```text
GET /api/learning/topics/search?q=...
```

Response:

```json
{
  "query": "...",
  "results": [
    {
      "id": "topic-id",
      "type": "feature",
      "title": "...",
      "summary": "...",
      "score": 0.91,
      "matched_fields": ["title", "summary"]
    }
  ]
}
```

### 7.4 Tutor

```text
POST /api/learning/tutor/chat
```

Request:

```json
{
  "message": "...",
  "stream": false,
  "context": {
    "page": "topic",
    "topic_id": "...",
    "path_id": "...",
    "lesson_id": "...",
    "selected_text": "..."
  },
  "learner": {
    "level": "beginner"
  }
}
```

Response:

```json
{
  "answer": "...",
  "summary": "...",
  "key_concepts": [],
  "citations": [],
  "suggested_questions": [],
  "recommended_next_steps": [],
  "related_topics": [],
  "graph_context": {
    "nodes": [],
    "relationships": []
  },
  "warnings": []
}
```

Streaming mode should use server-sent events for the no-build dashboard:

```text
POST /api/learning/tutor/chat?stream=true
```

Event types:

- `status`
- `token`
- `citation`
- `suggested_questions`
- `recommended_next_steps`
- `done`
- `error`

### 7.5 Progress

```text
GET /api/learning/progress
```

Response:

```json
{
  "completed_lessons": [
    {
      "path_id": "architecture-overview",
      "lesson_id": "lesson-1",
      "completed_at": "2026-06-02T00:00:00"
    }
  ],
  "viewed_topics": [
    {
      "topic_id": "topic-id",
      "viewed_at": "2026-06-02T00:00:00"
    }
  ],
  "preferred_explanation_level": "beginner",
  "active_learning_goal": "Understand retrieval pipeline",
  "last_visited_context": {
    "page": "topic",
    "topic_id": "topic-id"
  }
}
```

```text
POST /api/learning/progress/events
```

Request:

```json
{
  "event_type": "topic_viewed",
  "context": {
    "topic_id": "topic-id",
    "path_id": null,
    "lesson_id": null
  },
  "metadata": {}
}
```

Response:

```json
{
  "accepted": true,
  "progress": {}
}
```

### 7.6 Recommendations

```text
GET /api/learning/recommendations
```

Response:

```json
{
  "recommendations": [
    {
      "id": "rec-1",
      "type": "continue_path",
      "label": "Continue Architecture overview",
      "reason": "You completed lesson 1 and lesson 2 is the next prerequisite.",
      "target": {
        "path_id": "architecture-overview",
        "lesson_id": "lesson-2",
        "topic_id": null
      },
      "score": 0.95,
      "signals": ["incomplete_path", "prerequisite"]
    }
  ]
}
```

## 8. LLM Strategy

### 8.1 Provider

The first implementation should continue using the project's existing CrewAI-oriented LLM integration where possible, rather than introducing a new provider abstraction too early.

Provider strategy:

- Use existing project LLM configuration as the default.
- Keep the tutor behind a small `TutorLLMClient` interface.
- Allow future providers without changing API contracts.
- Keep a deterministic no-LLM fallback for local development and tests.

### 8.2 Streaming

Tutor chat should support streaming because answer latency strongly affects UX.

Implementation guidance:

- Use server-sent events for the no-build web dashboard.
- Keep non-streaming JSON response as the default and test baseline.
- Stream answer tokens first, then citations and next-step metadata as structured events.
- Fall back to non-streaming when provider or client does not support streaming.

### 8.3 Prompt Management

Prompts should be versioned and kept outside core business logic.

Recommended structure:

```text
kb_agent/learning/prompts/
    tutor_answer.v1.txt
    topic_explainer.v1.txt
    path_planner.v1.txt
```

Prompt requirements:

- include answer shape instructions
- require natural language
- require citations when available
- forbid raw graph-first responses
- define fallback behavior for missing context
- include a prompt version in generated metadata

Prompt versioning rules:

- Include `prompt_version` in topic page metadata, tutor response metadata, and cache keys.
- Link prompt version with KB version and provider model in every generated artifact.
- Bump from `v1` to `v2` when answer shape, required fields, citation behavior, safety rules, or generation semantics change.
- Do not bump the version for typo-only edits that do not affect generated output.
- Invalidate cached tutor and topic responses when KB version, prompt version, provider model, or explanation level changes.

## 9. Frontend Architecture

Recommended no-build structure for the first complete version:

```text
kb_agent/dashboard/static/
    index.html
    styles.css
    app.js
    api.js
    router.js
    state.js
    events.js
    views/
        dashboard.js
        learning_paths.js
        topic_page.js
        tutor.js
        graph_explorer.js
    components/
        progress.js
        citations.js
        topic_card.js
        lesson_step.js
        chat_panel.js
        recommendation_list.js
```

### 9.1 Routing

Use hash-based routing for the no-build dashboard:

- `#/dashboard`
- `#/paths`
- `#/paths/:pathId`
- `#/topics/:topicId`
- `#/tutor`
- `#/graph`

Hash routing keeps local dashboard serving simple and avoids backend rewrite rules.

### 9.2 State Management

Use a small event-driven store.

State slices:

- `route`
- `dashboard`
- `paths`
- `topics`
- `chat`
- `progress`
- `recommendations`

Pattern:

- API modules fetch data.
- Treat state as read-only and replace state slices on update.
- Use simple copy-on-write updates, such as object spread or shallow cloned objects.
- Optionally use `Object.freeze()` in development to catch accidental mutation.
- Views subscribe to store events.
- Components receive data through explicit render props.

### 9.3 Chat Panel

Support both:

- side panel on dashboard, path, topic, and graph pages
- full-page tutor view for focused conversations

The side panel should always carry current context. The full-page view should allow context-free questions and show recent learning context.

### 9.4 Component Communication

Use explicit events:

- `topic:selected`
- `path:started`
- `lesson:completed`
- `chat:send`
- `context:changed`
- `recommendations:refresh`

Avoid hidden cross-component mutation. Components should call action functions or emit events, not directly modify unrelated state.

## 10. UI Requirements

### 10.1 Navigation

Primary navigation:

- Dashboard
- Learning Paths
- Topics
- AI Tutor
- Graph Explorer

### 10.2 Dashboard Layout

Dashboard sections:

- learning status
- recommended next step
- active paths
- important features
- recent activity

### 10.3 Topic Layout

Topic page sections:

- explanation
- source references
- prerequisites
- related topics
- examples
- graph neighborhood

### 10.4 Tutor Layout

Tutor panel sections:

- conversation
- citations
- suggested questions
- recommended next step
- current context indicator

## 11. Data Storage

### 11.1 Platform Data

Store platform state separately from generated KB data.

Recommended initial storage:

```text
.kb/learning/
    paths.json
    topics.json
    progress.json
    events.jsonl
    recommendations.json
    tutor_cache.json
```

`events.jsonl` is append-only. `tutor_cache.json` should be a dictionary keyed by stable cache key for fast lookup.

### 11.2 Generated Vs User State

Generated data:

- paths
- topic summaries
- recommendations
- cached tutor responses

User state:

- progress
- preferences
- viewed topics
- completed lessons
- active learning goal
- last visited context

Keep these separate so regenerating knowledge does not erase user progress.

## 12. Degradation And Edge Cases

### 12.1 Empty Or Missing Knowledge Graph

If the graph is empty or missing:

- dashboard should show KB status and setup guidance
- topic/path endpoints should return empty results with warnings
- tutor should answer only from available manifest or source snippets
- graph explorer should show an empty state, not a broken canvas

### 12.2 LLM Not Configured

If no LLM is configured:

- use extractive summaries from KB entries
- show source snippets
- generate rule-based suggested questions
- return structured response objects
- mark `warnings` with `llm_unavailable`

### 12.3 Missing Citations

If a topic has no citations:

- show the explanation with a warning
- clearly mark source grounding as unavailable
- prefer linking related files or symbols when exact line citations cannot be resolved
- avoid strong claims that require source grounding

### 12.4 Circular Dependencies In Path Generation

If prerequisite detection finds circular dependencies:

- break cycles using graph centrality and hot-path score
- include cycle warnings in path metadata
- cap traversal depth
- avoid blocking the entire path generation

### 12.5 Large Graphs

If the graph is large:

- cap graph context returned to the UI
- paginate topic search
- limit path generation candidates
- compute centrality and hot-path signals offline when possible

## 13. Performance Strategy

### 13.1 Topic Explanation Generation

Use a hybrid approach:

- pre-generate summaries for high-value topics during KB build or dashboard warmup
- generate long explanations on demand
- cache generated topic pages by topic id, KB version, prompt version, and provider model

### 13.2 Tutor Response Cache

Cache only safe, reusable tutor responses.

Cache key should include:

- normalized message
- context ids
- KB version
- prompt version
- explanation level
- provider model

Do not cache responses with selected text unless the selected text is included in the key.

Cache invalidation:

- drop entries when KB version changes
- drop entries when prompt version changes
- drop entries when provider model changes
- optionally cap cache size and remove least recently used entries when `tutor_cache.json` grows too large

### 13.3 Path Generation

Path generation should not block dashboard load.

Implementation guidance:

- compute starter paths lazily or during KB build
- cap candidate nodes by feature importance, hot-path, and graph centrality
- persist generated paths to `.kb/learning/paths.json`
- regenerate only when KB version changes

### 13.4 Streaming UX

For tutor chat:

- show immediate status event
- stream tokens when available
- render citations as soon as they are resolved
- show suggested questions after final answer

## 14. Implementation Roadmap

### Phase 1: Platform Contracts And Models - Completed

Goal: define the platform shape before UI polish.

Deliverables:

- learning models
- API response contracts
- citation model
- progress event model
- prompt template folder
- basic tests for serialization and API shape

Acceptance criteria:

- Done: all learning APIs return deterministic placeholder data.
- Done: frontend can consume structured responses.
- Done: no endpoint returns raw graph data as the primary user-facing answer.
- Done: progress events and lesson completion persist lightweight single-user state.
- Done: storage can be injected through the read-only storage interface.

### Phase 2: Natural-Language Tutor

Goal: make chatbot behave like an AI tutor.

Deliverables:

- `learning/tutor.py`
- `TutorLLMClient`
- answer synthesizer prompt
- context builder integration
- citations
- suggested questions
- non-streaming response
- streaming response when provider supports it
- fallback without LLM

Acceptance criteria:

- chat responses are natural language
- citations are attached when available
- graph nodes and relationships are returned only as supporting context
- no-LLM fallback returns a useful structured answer

### Phase 3: Topic Pages - Completed

Goal: turn nodes/features/modules into learner-friendly pages.

Deliverables:

- topic API
- topic explainer
- topic search
- topic UI
- source citation component
- topic cache

Acceptance criteria:

- Done: user can open a topic and understand it without reading raw graph data
- Done: topic page includes explanation, citations when available, prerequisites, and related topics

### Phase 4: Learning Paths

Goal: guide users through the codebase.

Deliverables:

- path generator
- curated starter paths
- lesson UI
- lesson completion state
- circular dependency handling

Acceptance criteria:

- dashboard recommends at least 3 paths when KB data is available
- user can complete lessons
- path progress is stored
- path generation does not block dashboard load

### Phase 5: Recommendation Engine

Goal: personalize next steps from graph signals and learner progress.

Deliverables:

- recommendation scoring
- dashboard recommendations
- continuation recommendations
- prerequisite-aware ranking

Acceptance criteria:

- recommendations change based on completed lessons, viewed topics, and active goal
- prerequisite topics are prioritized before advanced topics

### Phase 6: Knowledge Explorer Polish

Goal: keep graph exploration useful but secondary.

Deliverables:

- readable relationship labels
- detail panel
- filters
- ask-about-node action
- graph context linked to topic pages

Acceptance criteria:

- graph explorer supports learning workflows
- clicking a node leads to a topic page or tutor context

### Phase 7: Platform Polish

Goal: make the product feel complete.

Deliverables:

- loading states
- empty states
- error states
- responsive layout
- keyboard-friendly navigation
- documentation update
- end-to-end tests

Acceptance criteria:

- platform is usable from dashboard to path to topic to tutor to graph
- test suite covers core learning APIs
- usage guide documents the learning platform workflow

## 15. Testing Strategy

Backend tests:

- learning model serialization
- tutor response shape
- streaming event shape
- citation resolver
- path generation
- circular dependency handling
- progress tracking
- recommendation ranking
- no-LLM fallback
- missing graph fallback

Frontend tests:

- dashboard renders recommendations
- path page renders lessons and completion state
- topic page renders citations and warnings
- tutor renders answer and suggested questions
- streaming tutor events update the chat panel
- graph explorer links to topic detail

Manual verification:

- run dashboard
- open learning dashboard
- start a path
- complete a lesson
- open a topic
- ask tutor a contextual question
- confirm recommendation changes
- confirm no-LLM fallback still renders useful content

## 16. Success Metrics

Product metrics:

- time to first useful explanation
- path start rate
- path completion rate
- number of contextual tutor follow-ups
- percentage of answers with citations
- percentage of sessions with a useful next action

Engineering metrics:

- API response determinism
- citation coverage
- test coverage for learning modules
- no raw graph-first answers in tutor responses
- stable dashboard loading time
- tutor first-token latency in streaming mode

## 17. Definition Of Done

The AI Learning Platform is complete when:

- Dashboard recommends what to learn next.
- Learning paths guide users through the repository.
- Topic pages explain concepts in natural language.
- AI tutor answers naturally with citations.
- Progress tracks viewed topics, completed lessons, active goal, and last context.
- Recommendations adapt to learner state.
- Graph explorer supports deeper inspection without being the default UI.
- Documentation explains the full learning workflow.
- Automated tests cover the core backend contracts.
