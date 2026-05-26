# Knowledge Base Agent

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-yellow)

Knowledge Base Agent là hạ tầng trí tuệ cho repository: biến source code của một hoặc nhiều dự án thành structured knowledge để AI agents có thể hiểu kiến trúc, flow, dependency và lấy đúng context khi reasoning.

Dự án này không được thiết kế như một chatbot cho code, một RAG wrapper đơn giản, hay một demo CrewAI. Hướng đi dài hạn là xây một lớp **Repository Intelligence Infrastructure**: kết hợp compiler intelligence, symbol graph, retrieval engine và AI reasoning để giúp agent làm việc với codebase lớn mà không phải đọc lại toàn bộ source mỗi lần.

## Quick Start

Yêu cầu cài đặt trước, xem phần [Cài Đặt](#cài-đặt) bên dưới. Sau đó có thể chạy nhanh trên chính repository này:

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2
python -m scripts.cli validate --kb .kb
python -m scripts.cli query "Parser làm gì?" --kb .kb --with-graph
```

Runtime telemetry, self-tuning, federation, and dashboard commands are optional layers on top of a graph snapshot:

```bash
python -m scripts.cli ingest-telemetry traces.json --kb .kb
python -m scripts.cli update-runtime-metadata --kb .kb
python -m scripts.cli train-ranking-model --kb .kb --min-samples 20
python -m scripts.cli auto-tune --kb .kb
python -m scripts.cli add-repo /path/to/other-project/.kb --name other-project --kb .kb
python -m scripts.cli resolve-cross-repo --kb .kb
python -m scripts.cli dashboard --kb .kb
```

Xem [Workflow Cho Nhiều Dự Án](#workflow-cho-nhiều-dự-án) để dùng tool với repository khác.

## Tư Tưởng Cốt Lõi

Nguyên tắc xuyên suốt của hệ thống là:

```text
Compiler Intelligence
  -> Graph Intelligence
  -> Retrieval Intelligence
  -> AI Reasoning
```

LLM không phải source of truth. LLM chỉ là lớp enrichment: tóm tắt, diễn giải, gợi ý ý nghĩa semantic, hoặc hỗ trợ reasoning sau khi hệ thống đã có dữ liệu nền đáng tin cậy.

Source of truth phải đến từ những nguồn deterministic hơn:

- parser
- compiler/semantic model
- symbol graph
- dependency graph
- provenance metadata
- confidence scoring

Mục tiêu không phải tạo tài liệu đẹp. Mục tiêu là **context precision**: agent cần biết đúng phần cần biết, không nhiều hơn và không ít hơn.

## Vì Sao Cần Hệ Thống Này

Khi một AI agent cần review PR, debug bug, onboard vào dự án mới, hoặc phân tích impact của thay đổi, nó thường phải tự đọc source code. Cách này tốn context, dễ bỏ sót quan hệ giữa các symbol, và khó tái sử dụng giữa nhiều agent.

Knowledge Base Agent giải quyết bằng cách phân tích repository một lần, tạo ra knowledge base có cấu trúc, rồi cho các agent query lại theo nhu cầu:

- Dự án này làm gì?
- Module này chứa những API nào?
- Function này được gọi bởi ai?
- Flow đăng nhập đi qua những class/function nào?
- Thay đổi file này ảnh hưởng đến vùng nào?
- Context nào là quan trọng nhất cho câu hỏi hiện tại?

## Kiến Trúc Hệ Thống

Knowledge Base Agent hoạt động theo pipeline: **Scanner → Parser → Symbol Graph → Materialized Views → FAISS Index → Retrieval Engine**.

Symbol Graph là trung tâm — source of truth duy nhất. Mọi thứ khác (KB entries, embeddings, context) là materialized views sinh ra từ graph. Chi tiết kiến trúc, design rationale, và hướng dài hạn tại [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Trạng Thái Hiện Tại

Hệ thống 5 phase đã hoàn thành đầy đủ (320 tests passing):

- Scanner/parser cho Python, C#, C++
- Symbol graph với graduated confidence
- 4 materialized views: `arch`, `mod`, `file`, `mem`
- Graph-aware retrieval với intent planning
- Cross-language bridging, temporal graph, hot-path
- Runtime telemetry, self-tuning retrieval, multi-repo federation
- **MCP Server** cho AI coding agents (Claude Code, Cursor, etc.)
- **Interactive web dashboard** với D3.js visualization
- **Incremental enrichment** và improved LLM resilience

Lịch sử chi tiết từng phase tại [docs/CHANGELOG.md](docs/CHANGELOG.md).

## Cài Đặt

Yêu cầu Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Các dependency phục vụ query/index:

- `sentence-transformers`
- `faiss-cpu`

## Workflow Cho Nhiều Dự Án

Thiết kế của tool là làm việc với nhiều repository, vì vậy workflow chuẩn là truyền rõ đường dẫn dự án bằng `--repo` và nơi ghi KB bằng `--out`.

Ví dụ Windows:

```bash
python -m scripts.cli analyze --repo "C:\path\to\project-a" --out "C:\path\to\project-a\.kb" --skip-ai --with-graph --depth 2
```

Ví dụ macOS/Linux:

```bash
python -m scripts.cli analyze --repo /path/to/project-a --out /path/to/project-a/.kb --skip-ai --with-graph --depth 2
```

Khuyến nghị cho snapshot mới là dùng graph mode. Legacy mode vẫn được giữ lại như fallback tương thích.

## CLI Reference

### Scan

```bash
python -m scripts.cli scan --repo /path/to/project-a
```

Liệt kê source files và ngôn ngữ detect được.

### Parse

```bash
python -m scripts.cli parse --repo /path/to/project-a
```

In ra symbols và imports được extract từ source code.

### Analyze

Legacy static snapshot:

```bash
python -m scripts.cli analyze --repo /path/to/project-a --out /path/to/project-a/.kb --skip-ai
```

Graph-aware static snapshot:

```bash
python -m scripts.cli analyze --repo /path/to/project-a --out /path/to/project-a/.kb --skip-ai --with-graph --depth 2
```

LLM enrichment có thể bật bằng cách bỏ `--skip-ai` và cấu hình `OPENAI_API_KEY`. Dùng `--skip-mem-ai` để bỏ AI cho MEM layer (tiết kiệm token khi repo lớn).

### Validate

```bash
python -m scripts.cli validate --kb /path/to/project-a/.kb
```

Kiểm tra consistency và orphan entries.

### Index

```bash
python -m scripts.cli index --kb /path/to/project-a/.kb
```

Build hoặc rebuild FAISS index từ KB entries hiện có.

### Query

Flat semantic query:

```bash
python -m scripts.cli query "AuthService làm gì?" --kb /path/to/project-a/.kb
```

Graph-aware query:

```bash
python -m scripts.cli query "AuthService được gọi bởi những gì?" --kb /path/to/project-a/.kb --with-graph
```

### Phase 4 Prerequisites

Telemetry, federation, and dashboard commands expect a graph-backed KB. Run `analyze --with-graph` first:

```bash
python -m scripts.cli analyze --repo /path/to/project-a --out /path/to/project-a/.kb --skip-ai --with-graph --depth 2
```

For federation, every external repository should also be analyzed with `--with-graph`, and `add-repo` should point at that repository's `.kb` directory containing `graph/`.

### Runtime Telemetry

Ingest OpenTelemetry-style trace spans after building a graph snapshot:

```bash
python -m scripts.cli analyze --repo /path/to/project-a --out /path/to/project-a/.kb --skip-ai --with-graph --depth 2
python -m scripts.cli ingest-telemetry /path/to/traces.json --kb /path/to/project-a/.kb
python -m scripts.cli update-runtime-metadata --kb /path/to/project-a/.kb
```

`traces.json` can be a list of spans, a single span object, or an object with a `spans` array:

```json
{
  "spans": [
    {
      "trace_id": "trace-1",
      "span_id": "span-1",
      "operation_name": "handle_request",
      "start_time": "2026-01-01T00:00:00",
      "end_time": "2026-01-01T00:00:00.125",
      "status_code": "OK",
      "attributes": {
        "code.filepath": "app/server.py",
        "code.function": "handle_request"
      }
    }
  ]
}
```

`ingest-telemetry` maps spans to graph nodes and stores them under `.kb/telemetry/`. `update-runtime-metadata` aggregates call counts, latency, and error-rate metadata from the ingested spans.

### Self-Tuning Retrieval

Train from collected feedback, apply the learned retrieval overrides, and inspect the active tuning stats:

```bash
python -m scripts.cli train-ranking-model --kb /path/to/project-a/.kb --min-samples 20
python -m scripts.cli auto-tune --kb /path/to/project-a/.kb
python -m scripts.cli show-tuning-stats --kb /path/to/project-a/.kb
```

`auto-tune` expects a tuning config produced by `train-ranking-model`. Once saved, graph-aware retrieval loads `.kb/telemetry/tuning_config.json` automatically.

Feedback collection is currently not exposed as a CLI command. Runtime or integration code should write feedback records into `.kb/telemetry/feedback.jsonl` before running `train-ranking-model`.

### Multi-Repo Federation

Register another repository's `.kb` directory, then resolve cross-repo references into the local graph:

```bash
python -m scripts.cli add-repo /path/to/project-b/.kb --name project-b --kb /path/to/project-a/.kb
python -m scripts.cli resolve-cross-repo --kb /path/to/project-a/.kb
python -m scripts.cli update-shared-deps --kb /path/to/project-a/.kb
```

Use this after each repository has been analyzed with `--with-graph`. `add-repo` records the external graph, while `resolve-cross-repo` persists namespaced foreign nodes and `REFERENCES_REPO` edges so graph-aware queries can traverse repository boundaries.

### Dashboard (Text)

Hiển thị graph health và retrieval analytics trong terminal:

```bash
python -m scripts.cli graph-health --kb /path/to/project-a/.kb
python -m scripts.cli query-analytics --kb /path/to/project-a/.kb
```

Example output includes node/edge counts, confidence distribution, orphan-node ratio, bridge and cross-repo edge counts, feedback volume, and useful-feedback rate.

### MCP Server

Start MCP server để AI coding agents (Claude Code, Cursor, etc.) query knowledge graph trực tiếp qua stdio transport:

```bash
python -m scripts.cli serve --kb /path/to/project-a/.kb
```

Với file watcher (auto-sync khi source thay đổi):

```bash
python -m scripts.cli serve --kb /path/to/project-a/.kb --watch
```

MCP server cung cấp 9 tools: `kb_search`, `kb_context`, `kb_callers`, `kb_callees`, `kb_impact`, `kb_node`, `kb_explore`, `kb_status`, `kb_files`.

Để tích hợp với Claude Code, thêm vào `.claude/settings.json`:

```json
{
  "mcpServers": {
    "kb-agent": {
      "command": "python",
      "args": ["-m", "scripts.cli", "serve", "--kb", ".kb"]
    }
  }
}
```

### Incremental Enrichment

Enrich KB entries chưa có AI data, không cần chạy lại toàn bộ pipeline:

```bash
python -m scripts.cli enrich --kb /path/to/project-a/.kb
```

Retry entries đã fail trước đó:

```bash
python -m scripts.cli enrich --kb /path/to/project-a/.kb --retry-failed
```

Chỉ enrich entries chưa có AI summary. Failures được log vào `.kb/telemetry/llm_failures.jsonl`.

### Web Dashboard

Launch interactive graph visualization trong browser (FastAPI + D3.js):

```bash
python -m scripts.cli dashboard --kb /path/to/project-a/.kb
```

Dashboard cung cấp force-directed graph visualization (D3.js), confidence visualization, hot-path highlighting, semantic search, và node detail panel. REST API tại `/api/*` endpoints.

### Troubleshooting

Common Phase 4 CLI failures usually mean a prerequisite artifact is missing:

| Message | Fix |
|---|---|
| `No graph found. Run analyze --with-graph first.` | Rebuild the KB with `python -m scripts.cli analyze --repo <repo> --out <repo>/.kb --skip-ai --with-graph --depth 2`. |
| `No traces found. Run ingest-telemetry first.` | Ingest traces with `python -m scripts.cli ingest-telemetry traces.json --kb <repo>/.kb`. |
| `No tuning config found. Run train-ranking-model first.` | Collect/write feedback to `.kb/telemetry/feedback.jsonl`, then run `train-ranking-model`. |
| External repo cannot be registered or resolved | Pass the external repository's `.kb` directory, and make sure it contains `graph/nodes.jsonl` and `graph/edges.jsonl`. |
| `No source files found. Run analyze first.` | Rebuild the KB with `python -m scripts.cli analyze --repo <repo> --out <repo>/.kb --skip-ai --with-graph --depth 2`. |
| `watchdog` not found for `--watch` | Install with `pip install watchdog>=3.0`. |

## Output

```text
/path/to/project-a/.kb/
  entries/                 # JSON materialized views: arch, mod, file, mem
  graph/                   # symbol graph data
    nodes.jsonl            # one JSON object per symbol node
    edges.jsonl            # one JSON object per relationship edge
    adjacency.json         # precomputed adjacency list for traversal
  index/                   # retrieval index
    faiss.index            # FAISS vector index
    id_map.json            # maps vector IDs to KB entry IDs
  telemetry/               # optional runtime traces, feedback, tuning config
  manifest.json            # snapshot metadata
  quality_report.json      # validation results
```

`.kb/` là generated output. Trong repo này, `.kb/` đang được ignore bởi Git.

## Roadmap

| Phase | Tên | Trạng thái | Tóm tắt |
|-------|-----|-----------|---------|
| Phase 1 | Graph-Aware MVP | **Đã hoàn thành** | Scanner, parser, symbol graph, materialized views, graph-aware retrieval |
| Phase 2 | Confident Graph | **Đã hoàn thành** | Enhanced resolution, confidence propagation, feature overlay, query planner |
| Phase 3 | Intelligent Retrieval | **Đã hoàn thành** | Cross-language bridging, temporal graph, hot-path, graph-aware embeddings |
| Phase 4 | Production Intelligence | **Đã hoàn thành** | Runtime telemetry, self-tuning retrieval, multi-repo federation, dashboard |
| Phase 5 | MCP + Dashboard | **Đã hoàn thành** | MCP server, interactive web dashboard, incremental enrichment, LLM resilience fixes |

## Nguyên Tắc Phát Triển

- Graph là source of truth; docs và KB entries là materialized views.
- Deterministic trước, probabilistic sau.
- Mọi semantic inference phải có confidence và provenance.
- Retrieval precision quan trọng hơn generation hay.
- Mỗi phase phải độc lập hữu dụng.
- Mỗi edge kind mới cần định nghĩa, confidence range và test cases.
- Không mở rộng complexity nếu chưa có benchmark chứng minh retrieval tốt hơn.

## Design Philosophy

Bài toán khó nhất không phải parser, graph database, embeddings hay LLM.

Bài toán khó nhất là **context precision**.

AI agent chỉ thật sự hữu ích khi nó biết đúng thứ cần biết, vào đúng thời điểm, với đúng mức chi tiết. Knowledge Base Agent được xây để trở thành lớp hạ tầng cho điều đó.

## License

MIT
