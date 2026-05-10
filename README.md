# Knowlegle Base Agent — MVP

Tổng quan
- Mục tiêu: chuyển toàn bộ mã nguồn (src) của một repository đa-ngôn ngữ thành tập tài liệu Markdown (human+agent readable) theo workflow: architecture → module → class → method.
- Đầu ra: cây Markdown trong docs/kb/ + sidecar JSON metadata (.kb/metadata/) + optional vector index.

MVP scope
- Input: toàn bộ thư mục src của repo.
- Ngôn ngữ MVP: Python, JavaScript/TypeScript, Java.
- Output cơ bản: README-like docs (architecture.md, modules, classes, methods) với YAML front-matter (metadata) cho mỗi MD.
- Orchestration: pipeline dạng workflow (CrewAI / task-runner) với sub-agents: scanner, language-detector, parser/extractor, summarizer, md-generator, indexer, ci-agent.

Quick start (local, MVP)
Prereqs (MVP)
- Python 3.10+
- pip
- git
- (Optional) Docker, Node.js

Suggested local steps (MVP)
1. Clone repo containing this agent.
2. Create virtualenv và cài dependencies:
   python -m venv .venv && .venv\Scripts\activate
   pip install -r requirements.txt
3. Chạy scan thử (CLI stub):
   kb-agent scan --repo /path/to/repo --out docs/kb
(Chi tiết CLI & configs sẽ có trong docs/MVP.md)

Output layout (MVP)
- docs/kb/
  - architecture.md
  - modules/<module>.md
  - classes/<class>.md
  - methods/<method>.md
- .kb/metadata/<relative-path>.json
- .kb/index/faiss.index (optional)

Schema tóm tắt
- MD front-matter (YAML) gồm:
  - id, kind (architecture/module/class/method), language, path, signature, summary, tags, source_commit, tests, links, confidence
- Sidecar JSON: đầy đủ provenance, parse evidence, embeddings ref

Tech stack (MVP)
- Orchestration: CrewAI (hoặc Prefect/Temporal as alternative)
- Language detection & parsing: GitHub Linguist heuristics + tree-sitter
- Summarization: LLM (OpenAI / local Llama2) với prompt templates
- Embeddings: OpenAI embeddings or sentence-transformers; index: FAISS (local) or Pinecone
- Storage: docs/kb in repo + .kb sidecar folder
- Runtime: Python for core workers; containerized workers for scale
- CI: GitHub Actions (diff-trigger → run pipeline → open PR with docs changes)

Quality & safety notes
- Exclude generated/vendor code by patterns
- Mark low-confidence items for manual triage
- Cache LLM outputs and batch calls to reduce cost
- Optionally run compiled examples/tests to ground summaries

Where to find detailed design
- See docs/MVP.md for data contracts, task message schemas, example MD, and MVP roadmap.

Contributing
- Add issues for missing language support or failing parsers.
- Follow code style and add tests for extractors.

License
- MIT (or adjust to your preferred license)