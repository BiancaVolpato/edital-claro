"""Text embeddings behind a small interface, so the model is configurable."""

from functools import lru_cache
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from app.core.config import get_settings

Vectors = NDArray[np.float32]


class EmbeddingProvider(Protocol):
    model_name: str

    def embed_passages(self, texts: list[str]) -> Vectors:
        """Embed documents. Returns one L2-normalized row per text."""
        ...

    def embed_queries(self, texts: list[str]) -> Vectors:
        """Embed search queries. Returns one L2-normalized row per text."""
        ...


class SentenceTransformerEmbeddings:
    """Local model loaded through sentence-transformers (default: multilingual-e5-base)."""

    def __init__(self, model_name: str) -> None:
        # Imported lazily: loading PyTorch takes seconds and tests never need it.
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name, device="cpu")
        # E5 models were trained with these prefixes and need them at inference time.
        self._is_e5 = "e5" in model_name.lower()

    def _encode(self, texts: list[str], prefix: str) -> Vectors:
        prepared = [f"{prefix}{text}" for text in texts] if self._is_e5 else texts
        vectors = self._model.encode(
            prepared, normalize_embeddings=True, show_progress_bar=False, batch_size=16
        )
        return np.asarray(vectors, dtype=np.float32)

    def embed_passages(self, texts: list[str]) -> Vectors:
        return self._encode(texts, "passage: ")

    def embed_queries(self, texts: list[str]) -> Vectors:
        return self._encode(texts, "query: ")


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """The configured embedding model, loaded once per process."""
    return SentenceTransformerEmbeddings(get_settings().embedding_model)
