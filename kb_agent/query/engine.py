from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from kb_agent.models.entry import KBEntry

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class QueryEngine:
    """Load FAISS index and query entries by semantic similarity."""

    def __init__(self, kb_dir: Path, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._kb_dir = kb_dir.resolve()
        self._model_name = model_name
        self._model = None
        self._index = None
        self._id_map: list[str] = []

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = self._load_model(SentenceTransformer, self._model_name)
        return self._model

    @staticmethod
    def _load_model(cls, model_name: str, retries: int = 2):
        """Load SentenceTransformer with retry for transient HTTP-client errors."""
        for attempt in range(retries):
            try:
                return cls(model_name)
            except RuntimeError as exc:
                if "client has been closed" in str(exc) and attempt < retries - 1:
                    continue
                raise

    def _load(self) -> None:
        if self._index is not None:
            return

        import faiss

        index_path = self._kb_dir / "index" / "faiss.index"
        id_map_path = self._kb_dir / "index" / "id_map.json"

        if not index_path.exists():
            raise FileNotFoundError(f"Index not found at {index_path}")

        self._index = faiss.read_index(str(index_path))
        self._id_map = json.loads(id_map_path.read_text(encoding="utf-8"))

    def query(self, question: str, top_k: int = 5) -> list[KBEntry]:
        self._load()

        model = self._get_model()
        q_vec = model.encode([question], show_progress_bar=False)
        q_vec_np = np.array(q_vec, dtype=np.float32)

        scores, indices = self._index.search(q_vec_np, min(top_k, len(self._id_map)))

        entries: list[KBEntry] = []
        for idx in indices[0]:
            if idx < 0:
                continue
            entry_id = self._id_map[idx]
            entry = self._load_entry(entry_id)
            if entry:
                entries.append(entry)

        return entries

    def _load_entry(self, entry_id: str) -> KBEntry | None:
        filename = entry_filename(entry_id)
        path = self._kb_dir / "entries" / filename
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return KBEntry(**data)


def entry_filename(entry_id: str) -> str:
    """Return the flat filename used for persisted KB entries."""
    stem = _FILENAME_SAFE_RE.sub("_", entry_id.replace(".", "_")).strip("_")
    return f"{stem or 'entry'}.json"
