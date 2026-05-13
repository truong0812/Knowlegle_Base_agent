"""Tests for KB indexer — build index, empty list, mock model."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

import pytest

from kb_agent.indexer.indexer import KBIndexer
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


@pytest.fixture
def mock_faiss(tmp_path: Path):
    mock_faiss_mod = MagicMock()

    def fake_write_index(index, path):
        Path(path).write_bytes(b"fake_index")

    mock_faiss_mod.write_index = fake_write_index
    mock_index = MagicMock()
    mock_faiss_mod.IndexFlatL2.return_value = mock_index

    with patch.dict(sys.modules, {"faiss": mock_faiss_mod}):
        yield mock_faiss_mod, mock_index


class TestKBIndexer:
    def test_build_index_writes_files(self, tmp_path: Path, mock_faiss):
        faiss_mod, mock_index = mock_faiss
        entries = [
            _make_entry("mem.test.func1", Layer.MEM, "func one"),
            _make_entry("mem.test.func2", Layer.MEM, "func two"),
        ]

        with patch.object(KBIndexer, "_get_model") as mock_get_model:
            mock_model = MagicMock()
            mock_model.encode.return_value = [[0.1] * 384, [0.2] * 384]
            mock_get_model.return_value = mock_model

            indexer = KBIndexer()
            indexer.build_index(entries, tmp_path / "index")

        assert (tmp_path / "index" / "faiss.index").exists()
        assert (tmp_path / "index" / "id_map.json").exists()

        id_map = json.loads((tmp_path / "index" / "id_map.json").read_text())
        assert id_map == ["mem.test.func1", "mem.test.func2"]

    def test_build_index_empty_list(self, tmp_path: Path):
        indexer = KBIndexer()
        indexer.build_index([], tmp_path / "index")

        assert not (tmp_path / "index" / "faiss.index").exists()

    def test_build_index_single_entry(self, tmp_path: Path, mock_faiss):
        faiss_mod, mock_index = mock_faiss
        entries = [_make_entry("arch.root", Layer.ARCH, "root")]

        with patch.object(KBIndexer, "_get_model") as mock_get_model:
            mock_model = MagicMock()
            mock_model.encode.return_value = [[0.5] * 384]
            mock_get_model.return_value = mock_model

            indexer = KBIndexer()
            indexer.build_index(entries, tmp_path / "index")

        id_map = json.loads((tmp_path / "index" / "id_map.json").read_text())
        assert len(id_map) == 1
