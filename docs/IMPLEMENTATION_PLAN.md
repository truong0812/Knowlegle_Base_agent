# MVP Implementation Tracker

## Tổng quan

| Phase | Nội dung | Trạng thái | Ngày bắt đầu | Ngày hoàn thành |
|---|---|---|---|---|
| 1 | Data Models | Not Started | - | - |
| 2 | Scanner | Not Started | - | - |
| 3 | Parser | Not Started | - | - |
| 4 | LLM + Analysis Pipeline | Not Started | - | - |
| 5 | Validator | Not Started | - | - |
| 6 | Indexer + Query | Not Started | - | - |
| 7 | CLI + Polish | Not Started | - | - |

---

## Phase 1 — Data Models

**Mục tiêu**: Định nghĩa toàn bộ Pydantic models là nền tảng cho mọi module khác.

| # | File | Nội dung | Trạng thái | Ghi chú |
|---|---|---|---|---|
| 1.1 | `kb_agent/__init__.py` | Package init, version | [ ] | |
| 1.2 | `kb_agent/models/__init__.py` | Re-export models | [ ] | |
| 1.3 | `kb_agent/models/entry.py` | Layer, SymbolKind, Language enums; Parameter, StaticData, AIData, KBEntry | [ ] | Core schema — mọi thứ phụ thuộc file này |
| 1.4 | `kb_agent/models/manifest.py` | KBStats, Manifest | [ ] | |
| 1.5 | `kb_agent/models/report.py` | CheckResult, QualityReport | [ ] | |
| 1.6 | `tests/fixtures/sample_python.py` | Sample Python source cho testing | [ ] | Class + methods + functions + imports |
| 1.7 | `tests/fixtures/sample_csharp.cs` | Sample C# source cho testing | [ ] | Namespace + class + methods + using |
| 1.8 | `tests/fixtures/sample_cpp.cpp` | Sample C++ source cho testing | [ ] | Namespace + class + functions + includes |
| 1.9 | `tests/conftest.py` | Shared fixtures (sample_repo, sample_entries, mock_llm) | [ ] | |

**Acceptance criteria**:
- [ ] Tất cả models serialize/deserialize đúng qua JSON
- [ ] `pytest tests/test_models.py` pass (nếu có)

---

## Phase 2 — Scanner

**Mục tiêu**: Quét repo, phát hiện ngôn ngữ, trả về danh sách files có metadata. Hỗ trợ `.kbignore`.

| # | File | Nội dung | Trạng thái | Ghi chú |
|---|---|---|---|---|
| 2.1 | `kb_agent/scanner/__init__.py` | Module init | [ ] | |
| 2.2 | `kb_agent/scanner/language.py` | `detect_language(path) -> Language | None`; extension map | [ ] | Chỉ Python, C#, C++ — trả None cho unsupported |
| 2.3 | `kb_agent/scanner/ignore.py` | `KbignoreMatcher` class — load .kbignore, match patterns | [ ] | Dùng fnmatch |
| 2.4 | `kb_agent/scanner/scanner.py` | `FileScanner` — walk repo, filter ignore, detect language, return `list[FileEntry]` | [ ] | FileEntry = pydantic model nhẹ |
| 2.5 | `tests/test_scanner.py` | Test scanner với tmp_path, test kbignore, test language detection | [ ] | |

**Acceptance criteria**:
- [ ] Scan sample repo → detect đúng ngôn ngữ cho .py, .cs, .cpp files
- [ ] Files trong .kbignore bị skip
- [ ] node_modules, .git, venv tự động skip

---

## Phase 3 — Parser

**Mục tiêu**: Parse source code thành symbols (classes, functions, imports) dùng tree-sitter cho cả 3 ngôn ngữ.

| # | File | Nội dung | Trạng thái | Ghi chú |
|---|---|---|---|---|
| 3.1 | `kb_agent/parser/__init__.py` | Module init | [ ] | |
| 3.2 | `kb_agent/parser/base.py` | `BaseParser` ABC; `SymbolInfo`, `ImportInfo`, `ParseResult` dataclasses | [ ] | Interface chung cho mọi parser |
| 3.3 | `kb_agent/parser/python_parser.py` | `PythonParser` — tree-sitter, fallback sang `ast` module | [ ] | Node types: class_definition, function_definition, import_statement |
| 3.4 | `kb_agent/parser/csharp_parser.py` | `CSharpParser` — tree-sitter | [ ] | Node types: class_declaration, method_declaration, namespace_declaration |
| 3.5 | `kb_agent/parser/cpp_parser.py` | `CppParser` — tree-sitter | [ ] | Node types: class_declaration, function_definition, namespace_definition |
| 3.6 | `kb_agent/parser/factory.py` | `get_parser(language: Language) -> BaseParser` | [ ] | Lazy import |
| 3.7 | `tests/test_parser.py` | Test parse fixtures, assert đúng symbols/imports/signatures | [ ] | Test cả 3 ngôn ngữ |

**Acceptance criteria**:
- [ ] Parse sample_python.py → extract đúng classes, functions, imports
- [ ] Parse sample_csharp.cs → extract đúng namespace, class, methods
- [ ] Parse sample_cpp.cpp → extract đúng namespace, class, functions
- [ ] Signatures reconstruct đúng
- [ ] Coverage ≥ 90% top-level symbols trên sample files

---

## Phase 4 — LLM + Analysis Pipeline

**Mục tiêu**: Xây 3-layer analysis pipeline. Layer trên làm context cho layer dưới. LLM sinh `ai` fields.

| # | File | Nội dung | Trạng thái | Ghi chú |
|---|---|---|---|---|
| 4.1 | `kb_agent/analyzer/__init__.py` | Module init | [ ] | |
| 4.2 | `kb_agent/analyzer/llm.py` | `LLMClient` — OpenAI API, file-based caching, batch processing | [ ] | Cache: SHA256(prompt) → JSON file |
| 4.3 | `kb_agent/analyzer/arch_layer.py` | `ArchitectureAnalyzer` — Layer 1: repo structure → arch entries | [ ] | Context: folder tree + manifests (<2K tokens) |
| 4.4 | `kb_agent/analyzer/mod_layer.py` | `ModuleAnalyzer` — Layer 2: files → module entries | [ ] | Context: L1 summary + symbol list (<4K tokens) |
| 4.5 | `kb_agent/analyzer/mem_layer.py` | `MemberAnalyzer` — Layer 3: symbols → member entries | [ ] | Context: L2 summary + source code (<4K tokens) |
| 4.6 | `kb_agent/analyzer/pipeline.py` | `AnalysisPipeline` — orchestrator: scan → parse → L1 → L2 → L3 → write | [ ] | Wire tất cả layers, build parent-child links |
| 4.7 | `tests/test_analyzer.py` | Test pipeline với skip_ai=True, mock LLM, assert entries đúng | [ ] | |

**Acceptance criteria**:
- [ ] Pipeline chạy end-to-end với `--skip-ai` → sinh entries chỉ có static fields
- [ ] Pipeline chạy với mock LLM → ai fields populated đúng schema
- [ ] Parent-child links đúng: arch → mod → mem
- [ ] Entry IDs tuân convention: arch.*, mod.*, mem.*

---

## Phase 5 — Validator

**Mục tiêu**: Tự động kiểm tra chất lượng KB — consistency, coverage, accuracy.

| # | File | Nội dung | Trạng thái | Ghi chú |
|---|---|---|---|---|
| 5.1 | `kb_agent/validator/__init__.py` | Module init | [ ] | |
| 5.2 | `kb_agent/validator/checks.py` | Individual checks: parent_consistency, orphan, signature_match, completeness, low_confidence | [ ] | |
| 5.3 | `kb_agent/validator/validator.py` | `KBValidator` — load entries, run all checks, produce QualityReport | [ ] | |
| 5.4 | `tests/test_validator.py` | Tạo entries có lỗi cố ý, assert validator detect đúng | [ ] | |

**Acceptance criteria**:
- [ ] Detect parent inconsistency
- [ ] Detect orphan entries
- [ ] Tính completeness ratio
- [ ] Flag entries có confidence < 0.7
- [ ] Output quality_report.json đúng schema

---

## Phase 6 — Indexer + Query

**Mục tiêu**: Build FAISS vector index từ entries, hỗ trợ semantic search qua CLI/HTTP.

| # | File | Nội dung | Trạng thái | Ghi chú |
|---|---|---|---|---|
| 6.1 | `kb_agent/indexer/__init__.py` | Module init | [ ] | |
| 6.2 | `kb_agent/indexer/indexer.py` | `KBIndexer` — sentence-transformers embedding + FAISS index | [ ] | Model: all-MiniLM-L6-v2 |
| 6.3 | `kb_agent/query/__init__.py` | Module init | [ ] | |
| 6.4 | `kb_agent/query/engine.py` | `QueryEngine` — load index, embed query, return top-k entries | [ ] | |
| 6.5 | `tests/test_indexer.py` | Test build index, test query trả relevant results | [ ] | |

**Acceptance criteria**:
- [ ] Build FAISS index từ entries
- [ ] Query trả top-3 relevant với precision ≥ 0.7 (manual check)
- [ ] Index save/load đúng

---

## Phase 7 — CLI + Polish

**Mục tiêu**: Wire tất cả modules vào CLI, update requirements, end-to-end test.

| # | File | Nội dung | Trạng thái | Ghi chú |
|---|---|---|---|---|
| 7.1 | `scripts/cli.py` | Wire scan, parse, analyze, validate, query đến implementation thực | [ ] | Hiện tại chỉ có stub |
| 7.2 | `requirements.txt` | Pin versions, thêm tree-sitter language bindings | [ ] | |
| 7.3 | E2E test | Chạy full pipeline trên tests/fixtures → verify manifest + entries + query | [ ] | |

**Acceptance criteria**:
- [ ] `python scripts/cli.py analyze --repo tests/fixtures --out .kb --skip-ai` chạy thành công
- [ ] `.kb/entries/` chứa đúng entries
- [ ] `.kb/manifest.json` đúng schema
- [ ] `python scripts/cli.py validate --kb .kb` → quality_report.json
- [ ] `python scripts/cli.py query "test" --kb .kb` → trả kết quả

---

## Notes

- Mỗi task đánh dấu `[x]` khi hoàn thành
- Cập nhật **Trạng thái** phase thành `In Progress` khi bắt đầu, `Done` khi tất cả tasks xong
- Ghi chú blocking issues hoặc decisions trong cột **Ghi chú**
