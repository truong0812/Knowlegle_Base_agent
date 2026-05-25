# Knowledge Base Agent — Các Vấn Đề Cần Cải Thiện

Updated: 2026-05-25

> Tất cả 5 issues dưới đây đã được giải quyết trong Phase 5 (commit `5bb5f9d`).

## 1. LLM Batch Processing & Rate Limiting — RESOLVED

**Giải pháp áp dụng (Phase 5A):**

- Giảm concurrency xuống 2 (từ 5), exponential backoff với 5 retries cho 429 errors
- Chunked batch processing với configurable `chunk_size`
- `--skip-mem-ai` flag cho phép bỏ AI cho MEM layer, tiết kiệm token
- Cache mechanism tránh gọi lại entries đã xử lý

**Files:** `kb_agent/analyzer/llm.py`, `kb_agent/analyzer/pipeline.py`

---

## 2. LLM Response Format Compatibility — RESOLVED

**Giải pháp áp dụng (Phase 5A):**

- Try JSON mode trước, fallback sang text parsing nếu model không hỗ trợ
- Tự động detect và retry không dùng `response_format` trên JSON decode error

**Files:** `kb_agent/analyzer/llm.py`

---

## 3. Progress Reporting — RESOLVED

**Giải pháp áp dụng (Phase 5A):**

- `progress_callback(stage, current, total)` parameter trong pipeline
- `tqdm` progress bars (graceful fallback nếu không có tqdm)

**Files:** `kb_agent/analyzer/pipeline.py`, `kb_agent/analyzer/mem_layer.py`, `kb_agent/analyzer/mod_layer.py`

---

## 4. Incremental AI Enrichment — RESOLVED

**Giải pháp áp dụng (Phase 5A):**

- New CLI command: `enrich --kb .kb [--retry-failed] [--batch-size 5]`
- `Enricher` class: scan entries thiếu AI data → gọi LLM → update entries → rebuild FAISS
- Chỉ xử lý entries chưa có AI summary, có thể chạy nhiều lần

**Files:** `kb_agent/analyzer/enricher.py`, `scripts/cli.py`

---

## 5. Error Resilience — RESOLVED

**Giải pháp áp dụng (Phase 5A):**

- Failure logging vào `.kb/telemetry/llm_failures.jsonl` với lý do fail
- `--retry-failed` flag cho phép retry chỉ entries đã fail
- Transient vs Permanent error classification (429/503/timeout vs 401/403/invalid model)

**Files:** `kb_agent/analyzer/llm.py`, `kb_agent/analyzer/enricher.py`
