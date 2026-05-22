# Knowledge Base Agent — Hướng Dẫn Sử Dụng

## Mục Lục

1. [Cài đặt](#cài-đặt)
2. [Quick Start](#quick-start)
3. [Phân tích Repository](#phân-tích-repository)
4. [Truy vấn Knowledge Base](#truy-vấn-knowledge-base)
5. [Telemetry Runtime](#telemetry-runtime)
6. [Self-Tuning Retrieval](#self-tuning-retrieval)
7. [Multi-Repo Federation](#multi-repo-federation)
8. [Dashboard & Observability](#dashboard--observability)
9. [Temporal Graph](#temporal-graph)
10. [Cấu hình LLM](#cấu-hình-llm)
11. [Troubleshooting](#troubleshooting)

---

## Cài đặt

### Yêu cầu

- Python 3.10+
- Git (tùy chọn, dùng cho temporal versioning)

### Cài đặt dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Cấu hình AI (tùy chọn)

Copy `.env.example` thành `.env` và điền thông tin:

```bash
cp .env.example .env
```

```env
# Bắt buộc nếu muốn dùng AI enrichment
OPENAI_API_KEY=sk-your-api-key-here

OPENAI_BASE_URL=https://api.openai.com/v1

OPENAI_MODEL=gausso4
```

Nếu không cấu hình, dùng `--skip-ai` để chạy ở chế độ static only.

---

## Quick Start

Phân tích chính repository này:

```bash
# Phân tích đầy đủ (static + graph)
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2

# Validate kết quả
python -m scripts.cli validate --kb .kb

# Truy vấn
python -m scripts.cli query "RetrievalEngine làm gì?" --kb .kb --with-graph
```

Kết quả được ghi vào thư mục `.kb/` (đã gitignore).

---

## Phân tích Repository

### Lệnh `scan` — Liệt kê source files

```bash
python -m scripts.cli scan --repo /path/to/project
```

Output: danh sách files với ngôn ngữ detect được. Dùng để kiểm tra trước khi phân tích.

### Lệnh `parse` — Xem symbols & imports

```bash
python -m scripts.cli parse --repo /path/to/project
```

Output: classes, functions, imports được extract từ source code. Không ghi file, chỉ in ra console.

### Lệnh `analyze` — Phân tích đầy đủ

Đây là lệnh chính, chạy toàn bộ pipeline: scan → parse → graph → views → index.

**Chế độ static only (không cần LLM):**

```bash
python -m scripts.cli analyze \
  --repo /path/to/project \
  --out /path/to/project/.kb \
  --skip-ai \
  --with-graph \
  --depth 2
```

**Chế độ full với AI enrichment:**

```bash
python -m scripts.cli analyze \
  --repo /path/to/project \
  --out /path/to/project/.kb \
  --with-graph \
  --depth 2
```

Yêu cầu `OPENAI_API_KEY` trong `.env`. Mỗi entry sẽ gọi LLM để sinh summary, purpose, tags. Kết quả được cache trong `.kb/.cache/` — lần chạy sau không gọi lại.

**Các flags:**

| Flag | Mặc định | Mô tả |
|------|----------|--------|
| `--repo` | `.` | Đường dẫn đến repository |
| `--out` | `.kb` | Thư mục output |
| `--skip-ai` | `false` | Bỏ qua LLM, chỉ phân tích static |
| `--with-graph` | `false` | Build symbol graph |
| `--depth` | `1` | Độ sâu grouping cho module view |
| `--model` | - | Tên LLM model |
| `--detect-bridges` | `false` | Detect cross-language bridges |
| `--version-id` | auto (git hash) | Nhãn cho temporal snapshot |

### Lệnh `validate` — Kiểm tra chất lượng

```bash
python -m scripts.cli validate --kb /path/to/project/.kb
```

Kiểm tra: parent consistency, orphan detection, coverage. Output: `quality_report.json`.

### Lệnh `index` — Build/rebuild FAISS index

```bash
# Index thường
python -m scripts.cli index --kb /path/to/project/.kb

# Index với graph-aware embeddings
python -m scripts.cli index --kb /path/to/project/.kb --with-graph
```

---

## Truy vấn Knowledge Base

### Flat semantic query

```bash
python -m scripts.cli query "AuthService làm gì?" --kb /path/to/project/.kb
```

Tìm kiếm semantic qua FAISS, trả về top-k entries phù hợp nhất.

### Graph-aware query (khuyến nghị)

```bash
python -m scripts.cli query "AuthService được gọi bởi những gì?" --kb /path/to/project/.kb --with-graph
```

Bao gồm: semantic search → graph expansion → context composition. Trả về symbols liên quan kèm relationships (calls, imports, contains...).

### Các loại query được hỗ trợ tự động

Hệ thống detect intent dựa trên câu hỏi:

| Câu hỏi ví dụ | Intent detected | Hành vi |
|---------------|----------------|---------|
| "RetrievalEngine làm gì?" | `SYMBOL_LOOKUP` | Chi tiết symbol + 1-hop context |
| "Login flow hoạt động thế nào?" | `FLOW_TRACE` | Trace call chain |
| "Module query chứa gì?" | `MODULE_OVERVIEW` | Overview module + files |
| "Ai gọi compose_context?" | `RELATIONSHIP` | Tìm callers/dependents |
| "Call chain từ X đến Y" | `CHAIN_TRACE` | Trace causal chain |
| "Code thay đổi gì sau PR #142?" | `VERSION_DIFF` | Diff temporal versions |

### Parameter `top_k`

```bash
python -m scripts.cli query "..." --kb .kb --top-k 10
```

Mặc định: 5 kết quả.

---

## Telemetry Runtime

Ingest runtime traces (OpenTelemetry) để thêm runtime metadata vào graph.

### Bước 1: Phân tích repository (đã có graph)

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2
```

### Bước 2: Ingest traces

Chuẩn bị file `traces.json`:

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

```bash
python -m scripts.cli ingest-telemetry traces.json --kb .kb
```

### Bước 3: Cập nhật runtime metadata

```bash
python -m scripts.cli update-runtime-metadata --kb .kb
```

Tính toán: call frequency, latency percentiles, error rates cho từng graph node.

### Output

```
.kb/telemetry/
  traces.jsonl          # Mapped trace spans
  runtime_metadata.json # Aggregated per-node metadata
```

Runtime metadata ảnh hưởng retrieval ranking — nodes có call frequency cao được ưu tiên.

---

## Self-Tuning Retrieval

Tự động điều chỉnh retrieval parameters dựa trên feedback.

### Bước 1: Thu thập feedback

Viết feedback vào `.kb/telemetry/feedback.jsonl`:

```jsonl
{"query": "AuthService làm gì?", "entry_id": "mem.auth.authservice", "useful": true}
{"query": "Parser gọi gì?", "entry_id": "mem.parser.parse_file", "useful": false}
```

### Bước 2: Train ranking model

```bash
python -m scripts.cli train-ranking-model --kb .kb --min-samples 20
```

Cần tối thiểu `--min-samples` feedback records. Model học từ useful/not useful labels.

### Bước 3: Apply auto-tuning

```bash
python -m scripts.cli auto-tune --kb .kb
```

Overrides được lưu vào `.kb/telemetry/tuning_config.json`. Graph-aware retrieval tự động load overrides.

### Kiểm tra tuning stats

```bash
python -m scripts.cli show-tuning-stats --kb .kb
```

---

## Multi-Repo Federation

Liên kết nhiều repositories thành một graph thống nhất.

### Bước 1: Phân tích từng repository riêng

```bash
python -m scripts.cli analyze --repo /path/to/project-a --out /path/to/project-a/.kb --skip-ai --with-graph --depth 2
python -m scripts.cli analyze --repo /path/to/project-b --out /path/to/project-b/.kb --skip-ai --with-graph --depth 2
```

### Bước 2: Đăng ký external repository

```bash
python -m scripts.cli add-repo /path/to/project-b/.kb --name project-b --kb /path/to/project-a/.kb
```

### Bước 3: Resolve cross-repo references

```bash
python -m scripts.cli resolve-cross-repo --kb /path/to/project-a/.kb
```

Tạo `REFERENCES_REPO` edges và namespaced foreign nodes trong local graph.

### Bước 4: Cập nhật shared dependencies

```bash
python -m scripts.cli update-shared-deps --kb /path/to/project-a/.kb
```

### Truy vấn cross-repo

Sau khi federation xong, graph-aware query tự động traverse qua repo boundaries:

```bash
python -m scripts.cli query "API endpoint nào gọi Python ML service?" --kb /path/to/project-a/.kb --with-graph
```

---

## Dashboard & Observability

### Dashboard tổng hợp

```bash
python -m scripts.cli dashboard --kb .kb
```

Hiển thị: node/edge counts, confidence distribution, orphan ratio, bridge counts, feedback stats.

### Graph health riêng

```bash
python -m scripts.cli graph-health --kb .kb
```

### Retrieval analytics riêng

```bash
python -m scripts.cli query-analytics --kb .kb
```

---

## Temporal Graph

Theo dõi sự thay đổi của graph theo thời gian qua các git commits.

### Xem các versions đã lưu

```bash
python -m scripts.cli versions --kb .kb
```

Mỗi lần chạy `analyze --with-graph`, một version snapshot được tự động tạo (dùng git commit hash).

### Diff giữa hai versions

```bash
python -m scripts.cli diff --from-version abc1234 --to-version def5678 --kb .kb
```

Hiển thị: nodes thêm/xóa/sửa, edges thêm/xóa/sửa giữa hai snapshots.

### Query temporal

```bash
python -m scripts.cli query "Code thay đổi gì sau commit gần nhất?" --kb .kb --with-graph
```

Intent `VERSION_DIFF` được detect tự động.

---

## Cấu hình LLM

### Biến môi trường

| Biến | Bắt buộc | Mặc định | Mô tả |
|------|----------|----------|--------|
| `OPENAI_API_KEY` | Có (nếu dùng AI) | — | API key |
| `OPENAI_BASE_URL` | Không | OpenAI default | Custom endpoint |
| `OPENAI_MODEL` | Không | `gpt-4o` | Tên model |

### Dùng OpenAI trực tiếp

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

### Dùng NVIDIA NIM

```env
OPENAI_API_KEY=nvapi-...
OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1
OPENAI_MODEL=meta/llama-3.1-70b-instruct
```

**Lưu ý:** NVIDIA API có rate limit chặt. LLM client tự động retry (3 lần) với exponential backoff. Giảm concurrency nếu cần bằng cách chỉnh `max_concurrency` trong `LLMClient`.

### Dùng Ollama (local)

```env
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=llama3
```

### Dùng Azure OpenAI

```env
OPENAI_API_KEY=your-azure-key
OPENAI_BASE_URL=https://your-resource.openai.azure.com/openai/deployments/your-deployment
OPENAI_MODEL=gpt-4o
```

### Override qua CLI

```bash
python -m scripts.cli analyze --repo . --out .kb --model gpt-4o-mini
```

Flag `--model` override `OPENAI_MODEL` env var.

---

## Troubleshooting

### Lỗi phổ biến

| Thông báo lỗi | Nguyên nhân | Cách fix |
|--------------|-------------|----------|
| `No graph found. Run analyze --with-graph first.` | Chưa build graph | `python -m scripts.cli analyze --repo <repo> --out <repo>/.kb --skip-ai --with-graph --depth 2` |
| `No traces found. Run ingest-telemetry first.` | Chưa ingest telemetry | `python -m scripts.cli ingest-telemetry traces.json --kb .kb` |
| `No tuning config found. Run train-ranking-model first.` | Chưa train model | Viết feedback vào `.kb/telemetry/feedback.jsonl`, rồi chạy `train-ranking-model` |
| `Error code: 429 - Too Many Requests` | LLM API rate limit | Client tự retry. Nếu vẫn lỗi nhiều, giảm `max_concurrency` trong `LLMClient` hoặc dùng provider khác |
| `Error code: 500 - NVLM_D2_Config` | Model không hỗ trợ text-only JSON | Đổi sang text-only model (vd: `meta/llama-3.1-70b-instruct`) |
| External repo cannot be registered | `.kb` thiếu graph data | Chạy `analyze --with-graph` trên external repo trước |

### Kiểm tra sức khỏe KB

```bash
python -m scripts.cli validate --kb .kb
python -m scripts.cli graph-health --kb .kb
```

### Rebuild từ đầu

```bash
rm -rf .kb
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2 --detect-bridges
```

### Xem cấu trúc output

```text
.kb/
  entries/                 # Materialized views (JSON)
  graph/                   # Symbol graph
    nodes.jsonl
    edges.jsonl
    adjacency.json
    features.jsonl
    hotpath.json
    versions/              # Temporal snapshots
  index/                   # FAISS vector index
    faiss.index
    id_map.json
  telemetry/               # Runtime data (optional)
  .cache/                  # LLM response cache
  manifest.json            # Snapshot metadata
  quality_report.json      # Validation results
```

---

## Workflow Tham Khảo

### Workflow cơ bản

```bash
# 1. Scan trước để kiểm tra
python -m scripts.cli scan --repo /path/to/project

# 2. Phân tích
python -m scripts.cli analyze --repo /path/to/project --out /path/to/project/.kb --skip-ai --with-graph --depth 2

# 3. Validate
python -m scripts.cli validate --kb /path/to/project/.kb

# 4. Query
python -m scripts.cli query "Entry point của ứng dụng?" --kb /path/to/project/.kb --with-graph
```

### Workflow full features

```bash
# 1. Phân tích với AI + bridges
python -m scripts.cli analyze --repo . --out .kb --with-graph --depth 2 --detect-bridges

# 2. Ingest runtime telemetry
python -m scripts.cli ingest-telemetry traces.json --kb .kb
python -m scripts.cli update-runtime-metadata --kb .kb

# 3. Federation với repo khác
python -m scripts.cli add-repo /other/.kb --name other --kb .kb
python -m scripts.cli resolve-cross-repo --kb .kb

# 4. Self-tuning
# ... thu thập feedback vào .kb/telemetry/feedback.jsonl ...
python -m scripts.cli train-ranking-model --kb .kb --min-samples 20
python -m scripts.cli auto-tune --kb .kb

# 5. Dashboard
python -m scripts.cli dashboard --kb .kb

# 6. Temporal
python -m scripts.cli versions --kb .kb
python -m scripts.cli diff --from-version v1 --to-version v2 --kb .kb
```

### Workflow phân tích project khác

```bash
# Windows
python -m scripts.cli analyze --repo "C:\projects\my-app" --out "C:\projects\my-app\.kb" --skip-ai --with-graph --depth 2

# macOS/Linux
python -m scripts.cli analyze --repo /projects/my-app --out /projects/my-app/.kb --skip-ai --with-graph --depth 2

# Query
python -m scripts.cli query "Database connection được quản lý thế nào?" --kb /projects/my-app/.kb --with-graph
```
