# Knowledge Base Agent — Các Vấn Đề Cần Cải Thiện

Updated: 2026-05-22

## 1. LLM Batch Processing & Rate Limiting

**Vấn đề:** Khi chạy AI enrichment cho repository lớn (887+ MEM entries), NVIDIA API trả 429 Too Many Requests liên tục. Pipeline hiện tại gửi requests song song qua `asyncio.gather` với semaphore=5, nhưng vẫn vượt rate limit.

**Triển vọng cải thiện:**

- **Giảm concurrency + tăng retry delay:** Giảm semaphore xuống 1-2, tăng retry delay lên 5-10 giây. Chậm nhưng ổn định hơn.
- **Bỏ AI cho MEM layer:** Chỉ gọi LLM cho arch + mod + file layers (~120 entries), bỏ 887 MEM entries. Nhanh hơn 10x, vẫn có AI overview cấp module/file.
- **Batch processing với interval:** Xử lý MEM entries theo batch nhỏ (5-10), chờ interval giữa các batch.
- **Tách 2 pass:** Chạy `--skip-ai` trước để tạo static KB nhanh, sau đó chạy script riêng chỉ gọi LLM cho entries chưa có cache. Có thể chạy lại nhiều lần cho đến khi hết cache miss.

**Files liên quan:** `kb_agent/analyzer/llm.py`, `kb_agent/analyzer/mem_layer.py`, `kb_agent/analyzer/pipeline.py`

---

## 2. LLM Response Format Compatibility

**Vấn đề:** Một số model không hỗ trợ `response_format: {"type": "json_object"}`. Ví dụ: `nvidia/llama-3.1-nemotron-nano-vl-8b-v1` (vision-language model) trả lỗi 500.

**Triển vọng cải thiện:**

- Detect model capability và fallback sang text parsing nếu model không hỗ trợ JSON mode.
- Hoặc thử JSON mode, nếu fail thì retry không dùng `response_format`.
- Validate model name trước khi gọi (warn nếu là VL model).

**Files liên quan:** `kb_agent/analyzer/llm.py`

---

## 3. Progress Reporting

**Vấn đề:** Khi chạy AI enrichment cho nhiều entries, không có tiến độ hiển thị. User không biết đã xử lý bao nhiêu / tổng bao nhiêu.

**Triển vọng cải thiện:**

- Thêm progress bar hoặc counter: `Processing MEM entries: 312/887 (35%)...`
- Log số entries thành công vs thất bại sau mỗi batch.
- Estimate thời gian còn lại dựa trên tốc độ xử lý trung bình.

**Files liên quan:** `kb_agent/analyzer/pipeline.py`, `kb_agent/analyzer/mem_layer.py`, `kb_agent/analyzer/mod_layer.py`

---

## 4. Incremental AI Enrichment

**Vấn đề:** Hiện tại nếu AI enrichment bị gián đoạn (rate limit, network error), phải chạy lại toàn bộ. Cache giúp không gọi lại entries đã có, nhưng pipeline vẫn phải đi qua toàn bộ flow.

**Triển vọng cải thiện:**

- Thêm lệnh CLI riêng: `enrich --kb .kb` — chỉ gọi LLM cho entries chưa có AI summary.
- Kiểm tra `.kb/.cache/` và `.kb/entries/` để xác định entries chưa được enrich.
- Cho phép chạy nhiều lần cho đến khi tất cả entries đều có AI data.

**Files liên quan:** `scripts/cli.py` (thêm command mới), `kb_agent/analyzer/pipeline.py`

---

## 5. Error Resilience

**Vấn đề:** Khi LLM call fail (429, 500, connection error), entry được ghi nhận nhưng không có AI data. Không có cơ chế retry sau đó cho riêng entries đó.

**Triển vọng cải thiện:**

- Log failed entries vào `.kb/telemetry/llm_failures.jsonl` với lý do fail.
- Cho phép retry chỉ các entries đã fail: `enrich --retry-failed --kb .kb`.
- Differentiate giữa transient errors (429, connection) và permanent errors (invalid model, wrong API key).

**Files liên quan:** `kb_agent/analyzer/llm.py`, `kb_agent/analyzer/pipeline.py`
