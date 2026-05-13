from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from kb_agent.models.entry import KBEntry


class KBIndexer:
    """Build FAISS vector index from KB entries using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def build_index(self, entries: list[KBEntry], out_dir: Path) -> None:
        if not entries:
            return

        model = self._get_model()

        # Build texts to embed
        texts: list[str] = []
        id_map: list[str] = []
        for entry in entries:
            text = f"{entry.id}: {entry.ai.summary or entry.static.signature or entry.static.kind.value}"
            texts.append(text)
            id_map.append(entry.id)

        embeddings = model.encode(texts, show_progress_bar=False)
        embeddings_np = np.array(embeddings, dtype=np.float32)

        # Build FAISS index
        import faiss

        dim = embeddings_np.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(embeddings_np)

        # Save
        out_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(out_dir / "faiss.index"))
        (out_dir / "id_map.json").write_text(json.dumps(id_map), encoding="utf-8")
