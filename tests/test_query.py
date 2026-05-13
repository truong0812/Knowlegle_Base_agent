"""Tests for Query engine — query, FileNotFoundError, entry loading."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb_agent.models.entry import AIData, KBEntry, Language, Layer, StaticData, SymbolKind


def _make_entry(entry_id: str, layer: Layer, summary: str = "test") -> KBEntry:
    return KBEntry(
        id=entry_id,
        layer=layer,
        static=StaticData(
            kind=SymbolKind.FUNCTION,
            language=Language.PYTHON,
            path="test.py",
            line_start=1,
            line_end=10,
            signature="def test()",
        ),
        ai=AIData(summary=summary, confidence=0.8),
    )


def _write_entry(kb_dir: Path, entry: KBEntry) -> None:
    entries_dir = kb_dir / "entries"
    entries_dir.mkdir(parents=True, exist_ok=True)
    filename = entry.id.replace(".", "_") + ".json"
    (entries_dir / filename).write_text(entry.model_dump_json(), encoding="utf-8")


class TestQueryEngine:
    def test_query_no_index_raises(self, tmp_path: Path):
        from kb_agent.query.engine import QueryEngine

        engine = QueryEngine(tmp_path)
        # faiss may not be installed, catch both errors
        with pytest.raises((FileNotFoundError, ImportError)):
            engine.query("test", top_k=3)

    def test_load_entry_with_L_separator(self, tmp_path: Path):
        from kb_agent.query.engine import QueryEngine

        entry = _make_entry("mem.test.myfunc_L42", Layer.MEM)
        _write_entry(tmp_path, entry)

        engine = QueryEngine(tmp_path)
        loaded = engine._load_entry("mem.test.myfunc_L42")
        assert loaded is not None
        assert loaded.id == "mem.test.myfunc_L42"

    def test_load_entry_not_found(self, tmp_path: Path):
        from kb_agent.query.engine import QueryEngine

        engine = QueryEngine(tmp_path)
        assert engine._load_entry("nonexistent") is None
