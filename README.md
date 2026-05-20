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

## Kiến Trúc Dài Hạn

### 1. Language Adapter

Hệ thống không giả vờ “language agnostic”. Mỗi ngôn ngữ nên có adapter riêng để tận dụng khả năng semantic tốt nhất:

| Ngôn ngữ | Adapter dài hạn | Fallback hiện tại |
|---|---|---|
| C# | Roslyn | tree-sitter |
| TypeScript | TypeScript Compiler API | tree-sitter trong tương lai |
| Python | Python `ast` | tree-sitter |
| C++ | clang tooling trong tương lai | tree-sitter |

### 2. CIR: Common Intermediate Representation

Mỗi adapter normalize dữ liệu về các schema chung, có version:

```text
cir.symbols.v1
cir.calls.v1
cir.dependencies.v1
cir.architecture.v1
```

CIR nên chứa:

- entities: package, module, file, class, method, function
- calls
- imports
- inheritance
- interface implementation
- type usages
- dependency relations
- provenance
- confidence
- commit/time metadata

### 3. Symbol Graph

Symbol Graph là trung tâm của hệ thống. Nó lưu các node và edge deterministic nhất có thể:

```text
SymbolNode:
  id
  kind
  language
  path
  line_start / line_end
  signature
  parameters
  return_type
  docstring

SymbolEdge:
  source
  target
  kind
  confidence
  source_type
  resolution
```

Các edge quan trọng:

- `contains`
- `imports`
- `calls`
- `inherits`
- `implements`
- `uses_type`

Rule quan trọng: thà thiếu edge còn hơn thêm edge sai. Edge có confidence thấp không nên được đưa vào graph mặc định.

### 4. Knowledge Materialization

Knowledge base không phải source of truth. Nó là lớp materialized views được sinh ra từ graph để phục vụ retrieval.

Các view hiện tại:

- `arch`: overview cấp repository
- `mod`: overview cấp module/folder
- `file`: overview cấp file
- `mem`: overview cấp class/function/method

Về lâu dài, materializer có thể sinh thêm:

- Markdown docs
- JSON/YAML context bundles
- Mermaid diagrams
- embeddings
- MCP payloads
- agent-specific context packs

### 5. Retrieval-Centric Design

Embeddings chỉ là một phần của retrieval, không phải toàn bộ retrieval.

Flow mong muốn:

```text
Query
  -> intent detection
  -> semantic seed search
  -> graph expansion
  -> architecture filtering
  -> dependency weighting
  -> confidence-aware ranking
  -> context composition
```

Context builder là thành phần khó nhất. Nó phải cân bằng:

- semantic relevance
- graph distance
- edge confidence
- architectural boundary
- token budget
- hot path/runtime importance trong tương lai

## Trạng Thái Hiện Tại

MVP hiện tại đã có nền móng đủ để chạy graph-aware snapshot:

- scanner cho Python, C#, C++
- parser dựa trên tree-sitter, Python có AST fallback
- legacy layered analysis: `arch`, `mod`, `mem`
- symbol graph
- graph-derived materialized views: `arch`, `mod`, `file`, `mem`
- FAISS semantic index
- graph-aware retrieval
- CLI cho `scan`, `parse`, `analyze`, `validate`, `index`, `query`
- runtime telemetry ingestion, retrieval self-tuning, multi-repo federation, observability dashboard

Các số liệu như test count và snapshot stats có thể thay đổi theo từng commit. Xem trạng thái gần nhất tại [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md).

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

LLM enrichment có thể bật bằng cách bỏ `--skip-ai` và cấu hình `OPENAI_API_KEY`.

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

### Dashboard

Show graph health and retrieval analytics together:

```bash
python -m scripts.cli dashboard --kb /path/to/project-a/.kb
```

For narrower output, use the split commands:

```bash
python -m scripts.cli graph-health --kb /path/to/project-a/.kb
python -m scripts.cli query-analytics --kb /path/to/project-a/.kb
```

Example output includes node/edge counts, confidence distribution, orphan-node ratio, bridge and cross-repo edge counts, feedback volume, and useful-feedback rate.

### Troubleshooting

Common Phase 4 CLI failures usually mean a prerequisite artifact is missing:

| Message | Fix |
|---|---|
| `No graph found. Run analyze --with-graph first.` | Rebuild the KB with `python -m scripts.cli analyze --repo <repo> --out <repo>/.kb --skip-ai --with-graph --depth 2`. |
| `No traces found. Run ingest-telemetry first.` | Ingest traces with `python -m scripts.cli ingest-telemetry traces.json --kb <repo>/.kb`. |
| `No tuning config found. Run train-ranking-model first.` | Collect/write feedback to `.kb/telemetry/feedback.jsonl`, then run `train-ranking-model`. |
| External repo cannot be registered or resolved | Pass the external repository's `.kb` directory, and make sure it contains `graph/nodes.jsonl` and `graph/edges.jsonl`. |

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

### Phase 1: Graph-Aware MVP

Đã hoàn thành ở mức nền tảng:

- scanner/parser
- symbol graph
- materialized views
- semantic index
- graph-aware retrieval

### Phase 2: Confident Graph

Mục tiêu là tăng độ tin cậy của graph và retrieval:

- enhanced symbol resolution
- alias/import resolution tốt hơn
- confidence propagation
- deterministic feature overlay
- benchmark queries cho retrieval precision

### Phase 3: Intelligent Retrieval

Mục tiêu là retrieval hiểu được flow lớn hơn:

- cross-language bridging
- graph-aware embeddings
- temporal graph
- advanced context composition
- hot-path prioritization

### Phase 4: Production Intelligence

Mục tiêu là đưa runtime và vận hành vào graph:

- OpenTelemetry/runtime traces
- latency/error/call-frequency metadata
- multi-repo graph
- retrieval observability
- self-tuning ranking

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
