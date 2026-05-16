# Retrieval Benchmarks

Mục tiêu của benchmark retrieval là đặt một thước đo ổn định cho Phase 2 trước khi cải thiện symbol resolution, confidence propagation hoặc query planner.

Các benchmark hiện tại nằm trong `tests/test_retrieval_benchmarks.py`. Chúng cố ý nhỏ và deterministic:

- Không tải embedding model thật.
- Không phụ thuộc FAISS thật.
- Mock semantic search để trả về seed entries đã biết.
- Kiểm tra phần graph-aware retrieval sau khi có seed bằng dữ liệu có cấu trúc trả về từ `RetrievalEngine`: intent, entry IDs, seed node IDs, expanded node IDs và `relationship_edges`.

## Gold Query Set

| Intent | Query | Expected structure |
|---|---|---|
| `symbol_lookup` | `What does RetrievalEngine do?` | seed node `RetrievalEngine`, expanded method nodes, `contains` edge |
| `flow_trace` | `How does graph retrieval work?` | seed node `retrieve`, expanded call targets, `calls` edges |
| `module_overview` | `overview of query module` | module entry fallback with no graph seed nodes |
| `relationship` | `Who calls compose_context?` | seed node `compose_context`, incoming caller node, `calls` edge |

## Metrics Được Lock

Benchmark assert trực tiếp trên:

- `result.metrics.intent`
- `result.entries[*].id`
- `result.metrics.seed_nodes`
- `result.metrics.expanded_nodes`
- `result.metrics.relationship_edges`

Điều này giữ benchmark ở mức integration: test chỉ gọi `RetrievalEngine.retrieve()`, không gọi lại mapper hoặc expander trong test. Nếu orchestration bên trong RetrievalEngine thay đổi làm mất seed/expanded nodes hoặc relationship edges quan trọng, benchmark sẽ fail.

## Cách Chạy

```bash
pytest tests/test_retrieval_benchmarks.py -q
```

Hoặc chạy toàn bộ test suite:

```bash
pytest -q
```

## Nguyên Tắc Mở Rộng

- Mỗi query mới nên có expected intent rõ ràng.
- Expected output nên dựa vào node IDs, entry IDs và edge tuples, không phụ thuộc văn bản dài.
- Benchmark nên deterministic để dùng được trong CI.
- Khi Phase 2 cải thiện retrieval, benchmark phải chứng minh được top-k/context chứa node đúng hơn, không chỉ output nghe hay hơn.
