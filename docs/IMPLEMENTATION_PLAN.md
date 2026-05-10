# Implementation Plan — MVP (Chi tiết)

Tổng quan ngắn: Triển khai MVP chuyển src → docs/kb/*.md + .kb/metadata/*.json + FAISS index + QA endpoint theo milestones M0..M6.

## Milestones & Tasks (chi tiết)

M0 — Preparation (1 ngày)
- Tạo scaffold repo: scripts/, .kb/, docs/kb/, requirements.txt, CLI stub. (DONE)
- Deliverable: README.md, docs/MVP.md, scripts/cli.py
- Acceptance: có thể chạy `python scripts/cli.py scan` trên repo mẫu.

M1 — Scanner & Language-Detector (3 ngày)
- Tasks:
  - Hoàn thiện CLI scan: thêm fast-glob/ripgrep integration, manifest checks (package.json, pom.xml, go.mod).
  - Implement ignore patterns configurable (.kbignore).
  - Output: .kb/artifacts/files.json (path, language, confidence, evidence).
- Acceptance:
  - files.json tồn tại, detection accuracy ≥95% trên sample set.
- Commands (dev):
  - python -m pip install -r requirements.txt
  - python scripts/cli.py scan --repo /path/to/sample --out .kb/artifacts

M2 — Parser / Extractor (7 ngày)
- Tasks:
  - Integrate tree-sitter bindings for Python/JS/Java.
  - Implement extractor worker that emits chunk sidecars: id, kind, signature, docstring, src_snippet, start/end lines.
  - Unit tests on 3 sample repos.
- Acceptance:
  - Extractor phát hiện ≥80% top-level symbols trong samples.
- Dev notes:
  - Keep extractor idempotent and deterministic.

M3 — Chunker & Call-Graph (3 ngày)
- Tasks:
  - Group chunks into architecture→module→class→method hierarchy.
  - Build simple static call-graph (name resolution heuristics).
  - Output module manifests + graph.json.
- Acceptance:
  - Parent links đúng ≥90% trong sample.

M4 — Summarizer & MD Generator (5 ngày)
- Tasks:
  - Implement summarizer interface (LLM adapter) + caching.
  - Prompt templates; batch summarization by module.
  - Render MD with YAML front-matter and body; save under docs/kb/.
- Acceptance:
  - ≥70% chunks có non-empty summary; YAML parses.

M5 — Embeddings, Indexer & QA endpoint (4 ngày)
- Tasks:
  - Compute embeddings (sentence-transformers) and build FAISS index.
  - Implement FastAPI endpoint: query → hybrid retrieval → return snippets.
- Acceptance:
  - Endpoint trả relevant top-3 với precision ≥0.7 (manual check).

M6 — CI integration & incremental diff (3 ngày)
- Tasks:
  - GitHub Actions workflow: diff-changed files → run pipeline on diffs → create PR with docs/kb updates.
  - Acceptance: PR created automatically with updated MDs on repo changes.

M7 — Human triage & Reporting (optional, 4 ngày)
- Tasks:
  - Generate low-confidence report; simple CSV or minimal web UI for manual edits.
  - Acceptance: reviewer can accept/modify before PR commit.

## Estimates & Team
- Total estimate: ~26–30 days (1 engineer full-time).
- Fast-track (MVP minimal): 10–14 days by narrowing scope (use OpenAI for summarization, skip call-graph accuracy, run sequentially).

## Acceptance Criteria (project-level)
- Generated docs/kb contains front-matter YAML matching schema.
- .kb/metadata contains sidecar JSON for each chunk.
- Local FAISS index built and QA endpoint runnable.
- CI creates PR with KB updates for code changes.

## Immediate next actions (choose one)
- A) Tôi bắt đầu M1: hoàn thiện scanner + language-agent (tôi sẽ tạo requirements.txt, .kbignore template, và nâng CLI).
- B) Bạn cung cấp sample repo để tôi chạy pipeline demo.
- C) Khác: chỉ định ngôn ngữ ưu tiên/limit scope.