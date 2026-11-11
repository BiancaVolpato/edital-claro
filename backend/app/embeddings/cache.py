"""On-disk cache of embeddings, so fixed texts are embedded only once.

Embedding the ~1,400 provisions of the law takes several minutes on a CPU, and
the result never changes for a given model and text. The cache file for the law
is committed to the repository: building the index (locally, in CI, in the
demo) then needs no model download and no computation. Texts that are not in
the cache fall through to the real model, which is loaded only in that case.
"""

import hashlib
from collections.abc import Callable
from pathlib import Path

import numpy as np

from app.embeddings.base import EmbeddingProvider, Vectors


class EmbeddingCacheMissError(LookupError):
    """A text is not in the cache and computing new embeddings is not allowed."""


def _key(kind: str, text: str) -> str:
    return hashlib.sha256(f"{kind}\n{text}".encode()).hexdigest()


class CachedEmbeddings:
    """Wraps an embedding provider with a file-backed cache keyed by text."""

    def __init__(
        self,
        model_name: str,
        path: Path,
        load_provider: Callable[[], EmbeddingProvider] | None,
    ) -> None:
        """``load_provider`` builds the real model on first miss; None forbids misses."""
        self.model_name = model_name
        self._path = path
        self._load_provider = load_provider
        self._provider: EmbeddingProvider | None = None
        self._vectors: dict[str, Vectors] = {}
        self._dirty = False
        if path.exists():
            with np.load(path, allow_pickle=False) as stored:
                if str(stored["model"]) != model_name:
                    raise ValueError(
                        f"{path.name} was built with '{stored['model']}', not '{model_name}'"
                    )
                matrix = stored["vectors"].astype(np.float32)
                # Stored as float16 to halve the file; re-normalize after the round trip.
                matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
                self._vectors = dict(zip(stored["keys"].tolist(), matrix, strict=True))

    def _embed(self, kind: str, texts: list[str]) -> Vectors:
        keys = [_key(kind, text) for text in texts]
        missing = [position for position, key in enumerate(keys) if key not in self._vectors]
        if missing:
            if self._load_provider is None:
                raise EmbeddingCacheMissError(
                    f"{len(missing)} text(s) are not in {self._path.name}; rebuild the cache"
                )
            self._provider = self._provider or self._load_provider()
            pending = [texts[position] for position in missing]
            computed = (
                self._provider.embed_passages(pending)
                if kind == "passage"
                else self._provider.embed_queries(pending)
            )
            for position, vector in zip(missing, computed, strict=True):
                self._vectors[keys[position]] = vector.astype(np.float32)
            self._dirty = True
        return (
            np.stack([self._vectors[key] for key in keys]) if keys else np.empty((0, 0), np.float32)
        )

    def embed_passages(self, texts: list[str]) -> Vectors:
        return self._embed("passage", texts)

    def embed_queries(self, texts: list[str]) -> Vectors:
        return self._embed("query", texts)

    def save(self) -> bool:
        """Write the cache back to disk if anything new was computed."""
        if not self._dirty:
            return False
        keys = sorted(self._vectors)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            self._path,
            model=np.array(self.model_name),
            keys=np.array(keys),
            vectors=np.stack([self._vectors[key] for key in keys]).astype(np.float16),
        )
        self._dirty = False
        return True
