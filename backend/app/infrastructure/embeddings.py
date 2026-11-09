"""Embedding provider interface.

Default: FastEmbed (ONNX, runs locally, no API key, no attendee data leaves the
server). `NullEmbeddingProvider` lets the whole product keep working with BM25
only when embeddings are disabled or the model cannot be loaded.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from app.config.settings import Settings

log = logging.getLogger(__name__)


class EmbeddingUnavailableError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    model_name: str
    dimensions: int

    @property
    def available(self) -> bool: ...

    def embed_passages(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


class NullEmbeddingProvider:
    model_name = "none"
    dimensions = 0

    def __init__(self, reason: str = "embeddings disabled") -> None:
        self.reason = reason

    @property
    def available(self) -> bool:
        return False

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        raise EmbeddingUnavailableError(self.reason)

    def embed_query(self, text: str) -> np.ndarray:
        raise EmbeddingUnavailableError(self.reason)


class FastEmbedProvider:
    def __init__(self, model_name: str, dimensions: int, cache_dir: Path | None = None) -> None:
        from fastembed import TextEmbedding  # local import: heavy

        self.model_name = model_name
        self.dimensions = dimensions
        self._model = TextEmbedding(
            model_name=model_name, cache_dir=str(cache_dir) if cache_dir else None
        )
        self._query_cache: dict[str, np.ndarray] = {}

    @property
    def available(self) -> bool:
        return True

    @staticmethod
    def _normalize(m: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(m, axis=-1, keepdims=True)
        norms[norms == 0] = 1.0
        return (m / norms).astype(np.float32)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        vecs = np.array(list(self._model.passage_embed(texts, batch_size=32)), dtype=np.float32)
        return self._normalize(vecs)

    def embed_query(self, text: str) -> np.ndarray:
        if text not in self._query_cache:
            vec = np.array(next(iter(self._model.query_embed([text]))), dtype=np.float32)
            if len(self._query_cache) > 512:
                self._query_cache.clear()
            self._query_cache[text] = self._normalize(vec[None, :])[0]
        return self._query_cache[text]


class ElasticInferenceEmbeddingProvider:
    """Embeddings from an Elasticsearch inference endpoint, e.g. `.jina-embeddings-v3` on the
    Elastic Inference Service (Elastic Cloud). Same interface as the local provider."""

    def __init__(self, inference_id: str, dimensions: int) -> None:
        from app.infrastructure.elasticsearch import get_es

        self.es = get_es()
        self.model_name = f"elastic:{inference_id}"
        self.inference_id = inference_id
        self.dimensions = dimensions
        self._query_cache: dict[str, np.ndarray] = {}

    # Elastic Inference Service accepts at most 16 inputs per request (measured, Serverless 9.7).
    batch_size = 16

    @property
    def available(self) -> bool:
        return True

    def _embed(self, texts: list[str], input_type: str) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            try:
                resp = self.es.inference.inference(
                    inference_id=self.inference_id,
                    task_type="text_embedding",
                    input=texts[i : i + self.batch_size],
                    input_type=input_type,
                )
            except Exception as exc:
                raise EmbeddingUnavailableError(f"inference endpoint failed: {exc}") from exc
            out += [e["embedding"] for e in resp["text_embedding"]]
        return FastEmbedProvider._normalize(np.array(out, dtype=np.float32))

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, "ingest")

    def embed_query(self, text: str) -> np.ndarray:
        if text not in self._query_cache:
            if len(self._query_cache) > 512:
                self._query_cache.clear()
            self._query_cache[text] = self._embed([text], "search")[0]
        return self._query_cache[text]


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "none":
        return NullEmbeddingProvider()
    if settings.embedding_provider == "elastic":
        return ElasticInferenceEmbeddingProvider(
            settings.elastic_embedding_inference_id, settings.embedding_dimensions
        )
    try:
        return FastEmbedProvider(
            settings.embedding_model,
            settings.embedding_dimensions,
            settings.resolved_model_cache_dir,
        )
    except Exception as exc:  # model download / onnxruntime failure
        log.warning("Embedding model unavailable, falling back to keyword-only: %s", exc)
        return NullEmbeddingProvider(f"embedding model failed to load: {exc}")


class EmbeddingCache:
    """Content-addressed on-disk cache so repeated ingestion does not re-embed."""

    def __init__(self, path: Path, model_name: str) -> None:
        self.path = path
        self.model_name = model_name
        self._data: dict[str, np.ndarray] = {}
        if path.exists():
            with np.load(path, allow_pickle=False) as npz:
                self._data = {k: npz[k] for k in npz.files}

    def key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model_name}\n{text}".encode()).hexdigest()[:32]

    def embed(self, provider: EmbeddingProvider, texts: list[str]) -> np.ndarray:
        keys = [self.key(t) for t in texts]
        missing = [(k, t) for k, t in zip(keys, texts, strict=True) if k not in self._data]
        if missing:
            vecs = provider.embed_passages([t for _, t in missing])
            for (k, _), v in zip(missing, vecs, strict=True):
                self._data[k] = v
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Persist the whole cache (not just this batch) so other callers' vectors survive.
            arrays: dict[str, Any] = dict(self._data)
            np.savez_compressed(self.path, **arrays)
        return np.stack([self._data[k] for k in keys])
