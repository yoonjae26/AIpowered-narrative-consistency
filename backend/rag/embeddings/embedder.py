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
    # Loading a SentenceTransformer is expensive (seconds) and, under repeated
    # reloads in the same process, can hit a PyTorch meta-tensor init error.
    # Cache the loaded model per process so each API request doesn't pay for
    # a fresh load — the model itself is stateless and safe to share.
    _model_cache: dict[str, object] = {}

    def __init__(self, model_name: str = "jhgan/ko-sroberta-multitask") -> None:
        self.model_name = model_name
        self._model = self._get_or_load_model(model_name)
        self._fallback = HashEmbedder()

    @classmethod
    def _get_or_load_model(cls, model_name: str):
        if SentenceTransformer is None:
            return None
        if model_name not in cls._model_cache:
            cls._model_cache[model_name] = SentenceTransformer(model_name)
        return cls._model_cache[model_name]

    def embed(self, text: str) -> list[float]:
        if self._model is None:
            return self._fallback.embed(text)

        vector = self._model.encode(text)
        return vector.tolist() if hasattr(vector, "tolist") else list(vector)