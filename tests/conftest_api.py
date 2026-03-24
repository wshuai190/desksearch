"""Shared test helpers — lightweight mock embedder to avoid loading torch/Starbucks.

The real Starbucks model triggers a SIGSEGV at process exit on Apple Silicon
due to torch + FAISS shared-library cleanup ordering. API tests don't need
the real model — a deterministic hash-based embedder is sufficient.
"""
import hashlib
import numpy as np
from desksearch.indexer.embedder import Embedder


class MockEmbedder(Embedder):
    """Drop-in replacement that produces deterministic embeddings without torch."""

    def __init__(self, embedding_dim: int = 64, **kwargs):
        # Bypass parent __init__ to avoid model-loading machinery
        self._target_dim = embedding_dim
        self._dimension = embedding_dim
        self._backend = "mock"
        self._model = "mock"  # truthy so is_loaded=True
        self._onnx_session = None
        self._tokenizer = None
        import threading
        from collections import OrderedDict
        self._lock = threading.Lock()
        self._last_used = 0.0
        self._unload_timer = None
        self._query_cache = OrderedDict()
        self._query_cache_lock = threading.Lock()
        self._chunk_cache = OrderedDict()
        self._chunk_cache_lock = threading.Lock()
        self._chunk_cache_hits = 0
        self._chunk_cache_misses = 0
        self.model_name = "mock"
        self.idle_timeout = 0

    def _ensure_loaded(self):
        pass

    def embed(self, texts: list[str], batch_size: int = 128) -> np.ndarray:
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, self._target_dim)
        vecs = np.zeros((len(texts), self._target_dim), dtype=np.float32)
        for i, t in enumerate(texts):
            h = hashlib.sha256(t.encode()).digest()
            for j in range(self._target_dim):
                vecs[i, j] = (h[j % len(h)] - 128) / 128.0
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-9)
        return vecs / norms

    def warmup(self):
        pass

    def cooldown(self):
        pass
