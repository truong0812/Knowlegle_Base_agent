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

    def build_index(
        self,
        entries: list[KBEntry],
        out_dir: Path,
        graph_dir: Path | None = None,
    ) -> None:
        if not entries:
            return

        model = self._get_model()

        # Build texts to embed
        embedder = self._get_graph_embedder(graph_dir)
        texts: list[str] = []
        id_map: list[str] = []
        for entry in entries:
            if embedder:
                text = embedder.enrich_text(entry)
            else:
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

    def _get_graph_embedder(self, graph_dir: Path | None):
        if graph_dir is None:
            return None
        try:
            from kb_agent.indexer.graph_embedding import GraphAwareEmbedder
            return GraphAwareEmbedder.from_graph_dir(graph_dir)
        except Exception:
            return None
