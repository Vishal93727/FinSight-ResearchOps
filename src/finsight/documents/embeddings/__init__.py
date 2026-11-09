"""Pluggable document embeddings with an explicit deterministic offline baseline.

`feature_hash_v1` is useful for tests and a zero-network local development path. It is
not a learned semantic embedding model. `sentence_transformers` enables a local learned
encoder when the optional `semantic` extra and model weights are installed.
"""
from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol, Sequence

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.'%-]*")


class EmbeddingProvider(Protocol):
    name: str
    model_name: str
    dimensions: int

    def embed(self, text: str) -> list[float]: ...


class FeatureHashEmbeddingProvider:
    name = "feature_hash_v1"

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions < 64 or dimensions > 4096:
            raise ValueError("Embedding dimensions must be between 64 and 4096")
        self.dimensions = dimensions
        self.model_name = "signed_unigram_bigram_hash_v1"

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = [token.lower() for token in TOKEN_RE.findall(text)]
        for index, token in enumerate(tokens):
            features: Sequence[tuple[str, float]] = ((token, 1.0),)
            if index + 1 < len(tokens):
                features = (*features, (f"{token}_{tokens[index + 1]}", 0.35))
            for feature, weight in features:
                digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
                value = int.from_bytes(digest, "big")
                slot = value % self.dimensions
                sign = 1.0 if (value >> 11) & 1 else -1.0
                vector[slot] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class SentenceTransformerEmbeddingProvider:
    """Lazy CPU-backed learned embeddings; model weights are cached by the library."""

    name = "sentence_transformers"

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        if not model_name or len(model_name) > 240:
            raise ValueError("A valid SentenceTransformer model name is required")
        self.model_name = model_name
        self._model = _load_sentence_transformer(model_name)
        self.dimensions = int(self._model.get_sentence_embedding_dimension())
        if self.dimensions <= 0 or self.dimensions > 4096:
            raise ValueError("SentenceTransformer model returned an unsupported embedding size")

    def embed(self, text: str) -> list[float]:
        values = self._model.encode([text], normalize_embeddings=True, convert_to_numpy=True)[0]
        return [float(value) for value in values.tolist()]


@lru_cache(maxsize=2)
def _load_sentence_transformer(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("Learned embeddings require the optional 'semantic' extra") from exc
    try:
        return SentenceTransformer(model_name, device="cpu")
    except Exception as exc:
        raise RuntimeError(
            f"Could not load embedding model {model_name!r}; install/cache the model weights first"
        ) from exc


def get_embedding_provider(provider_name: str = "feature_hash_v1", dimensions: int = 384,
                           model_name: str | None = None) -> EmbeddingProvider:
    if provider_name == "feature_hash_v1":
        return FeatureHashEmbeddingProvider(dimensions)
    if provider_name == "sentence_transformers":
        return SentenceTransformerEmbeddingProvider(
            model_name or "sentence-transformers/all-MiniLM-L6-v2"
        )
    raise ValueError(f"Unsupported embedding provider: {provider_name}")


def embed_text(text: str, dimensions: int = 384) -> list[float]:
    """Backward-compatible deterministic embedding helper for tests and Phase 2 callers."""
    return FeatureHashEmbeddingProvider(dimensions).embed(text)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    return float(sum(a * b for a, b in zip(left, right)))
