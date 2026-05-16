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
