from __future__ import annotations

from abc import ABC, abstractmethod
from hashlib import sha256

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None


class BaseEmbedder(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class HashEmbedder(BaseEmbedder):
    def __init__(self, dimensions: int = 32) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        digest = sha256(text.encode("utf-8")).digest()
        values = [b / 255.0 for b in digest]

        if len(values) >= self.dimensions:
            return values[: self.dimensions]
        return values + [0.0] * (self.dimensions - len(values))


class SentenceTransformerEmbedder(BaseEmbedder):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = SentenceTransformer(model_name) if SentenceTransformer else None
        self._fallback = HashEmbedder()

    def embed(self, text: str) -> list[float]:
        if self._model is None:
            return self._fallback.embed(text)

        vector = self._model.encode(text)
        return vector.tolist() if hasattr(vector, "tolist") else list(vector)