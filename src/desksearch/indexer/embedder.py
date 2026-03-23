"""Local embedding with ONNX Runtime (low memory) or sentence-transformers fallback.

Default path uses ONNX Runtime + HuggingFace tokenizers for ~200MB RAM.
Falls back to sentence-transformers (~1.4GB RAM) if onnxruntime is not installed.

The model is loaded lazily on first use and auto-unloaded after idle timeout.

Chunk-level embedding cache: ``embed_with_cache()`` accepts a list of texts and
an optional parallel list of content keys (e.g. SHA-256 hashes of the chunk
text).  Cache hits are returned directly; only misses go to ONNX inference.
This accelerates re-indexing of partially modified files and large corpora that
share many repeated chunks (boilerplate, headers, etc.).
"""
import gc
import hashlib
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional

import numpy as np

from desksearch.config import DEFAULT_EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_DEFAULT_IDLE_TIMEOUT = 300  # 5 minutes

# HuggingFace ONNX model repo for all-MiniLM-L6-v2
_ONNX_MODEL_REPO = "sentence-transformers/all-MiniLM-L6-v2"
_ONNX_MODEL_FILE = "onnx/model.onnx"
_ONNX_DIMENSION = 384  # Known dimension for all-MiniLM-L6-v2


def _onnx_available() -> bool:
    """Check if onnxruntime is installed."""
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def _sentence_transformers_available() -> bool:
    """Check if sentence-transformers is installed."""
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


class Embedder:
    """Wraps an embedding model for generating embeddings.

    Prefers ONNX Runtime (low memory) and falls back to sentence-transformers.
    The model is loaded lazily, cached, and auto-unloaded after idle.
    """

    # Maximum number of single-query embeddings to cache.
    # Memory cost: _QUERY_CACHE_SIZE * 384 * 4 bytes ≈ 512 * 384 * 4 ≈ 768 KB
    _QUERY_CACHE_SIZE = 512

    # Maximum number of chunk embeddings to cache across index runs.
    # Memory cost: _CHUNK_CACHE_SIZE * 384 * 4 bytes ≈ 8192 * 384 * 4 ≈ 12 MB
    # This covers ~64 documents at ~128 chunks each — plenty for re-index runs.
    _CHUNK_CACHE_SIZE = 8192

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        idle_timeout: float = _DEFAULT_IDLE_TIMEOUT,
        embedding_dim: int = 64,
    ) -> None:
        self.model_name = model_name
        self.idle_timeout = idle_timeout
        self._target_dim = embedding_dim  # Matryoshka truncation target

        self._model = None          # SentenceTransformer or None
        self._onnx_session = None   # onnxruntime.InferenceSession or None
        self._tokenizer = None      # AutoTokenizer or None
        self._backend: Optional[str] = None  # "onnx" or "sentence_transformers"
        self._lock = threading.Lock()
        self._last_used: float = 0.0
        self._unload_timer: Optional[threading.Timer] = None
        self._dimension: Optional[int] = None

        # LRU cache for single-query embeddings.  Keyed on the raw query string.
        # Thread-safe because reads/writes are protected by _query_cache_lock.
        self._query_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._query_cache_lock = threading.Lock()

        # LRU cache for chunk embeddings.  Keyed on SHA-256 hex digest of the
        # chunk text.  Populated by embed_with_cache(); allows re-indexing of
        # partially-changed files without re-embedding identical chunks.
        self._chunk_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._chunk_cache_lock = threading.Lock()
        # Stats for observability
        self._chunk_cache_hits: int = 0
        self._chunk_cache_misses: int = 0

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        """Whether the embedding model is currently in memory."""
        return self._model is not None or self._onnx_session is not None

    @property
    def backend(self) -> Optional[str]:
        """Return which backend is active: 'onnx' or 'sentence_transformers'."""
        return self._backend

    def _get_onnx_model_path(self) -> Path:
        """Download/cache the ONNX model and return its path.

        Raises a user-friendly RuntimeError when the download fails so the
        operator gets actionable guidance rather than a cryptic traceback.
        """
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise RuntimeError(
                "huggingface_hub is required to download the ONNX model. "
                "Install it with: pip install huggingface-hub"
            ) from exc

        try:
            model_path = hf_hub_download(
                repo_id=_ONNX_MODEL_REPO,
                filename=_ONNX_MODEL_FILE,
            )
        except Exception as exc:
            # Provide concrete, actionable error guidance.
            hint = (
                f"Failed to download ONNX model '{_ONNX_MODEL_REPO}/{_ONNX_MODEL_FILE}'.\n"
                "Possible causes and fixes:\n"
                "  1. No internet connection — connect and retry, or pre-cache the model.\n"
                "  2. HuggingFace rate-limit — wait a moment and retry.\n"
                "  3. Offline environment — set HF_HUB_OFFLINE=1 and ensure the model\n"
                f"     is cached in ~/.cache/huggingface/hub/ (run once online first).\n"
                "  4. Proxy/firewall — set HTTPS_PROXY or HF_ENDPOINT env vars.\n"
                f"Original error: {exc}"
            )
            raise RuntimeError(hint) from exc

        return Path(model_path)

    def _ensure_loaded(self):
        """Load the model if not already loaded (thread-safe)."""
        if self._onnx_session is not None or self._model is not None:
            self._touch()
            return

        with self._lock:
            if self._onnx_session is not None or self._model is not None:
                self._touch()
                return

            t0 = time.perf_counter()

            if _onnx_available() and self.model_name == DEFAULT_EMBEDDING_MODEL:
                self._load_onnx()
            elif _sentence_transformers_available():
                self._load_sentence_transformers()
            else:
                raise RuntimeError(
                    "No embedding backend available. Install onnxruntime "
                    "(recommended, low memory) or sentence-transformers."
                )

            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                "Model loaded in %.0fms via %s backend. Dimension: %d",
                elapsed, self._backend, self._dimension,
            )
            self._touch()

    def _load_onnx(self) -> None:
        """Load the ONNX model + lightweight tokenizer."""
        import onnxruntime as ort
        from tokenizers import Tokenizer

        logger.info("Loading ONNX embedding model: %s", self.model_name)

        # Download/cache the ONNX model
        model_path = self._get_onnx_model_path()

        # Configure ONNX Runtime for maximum throughput on Apple Silicon.
        #
        # Benchmarks on M-series Mac mini (8-core, 4P+4E):
        #   threads=4 → ~376 texts/sec   ← optimal (P-cores only)
        #   threads=6 → ~359 texts/sec
        #   threads=8 → ~339 texts/sec   (E-cores add overhead)
        #
        # Keep intra_op at 4 to hit the performance cores and leave the rest
        # for parallel parse workers and the OS.  On non-Apple machines the
        # heuristic of "half the logical CPUs, capped at 8" is still applied.
        import os as _os
        import platform as _platform
        _ncpus = _os.cpu_count() or 4
        _is_apple_silicon = (
            _platform.system() == "Darwin"
            and _platform.machine() in ("arm64", "aarch64")
        )
        if _is_apple_silicon:
            # Performance cores only: typically 4 on M1/M2, 6 on M3 Pro+
            _intra = min(4, _ncpus)
            _inter = 1
        else:
            _intra = min(_ncpus // 2, 8)
            _inter = min(max(_ncpus // 4, 1), 2)

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = _intra
        sess_options.inter_op_num_threads = _inter
        # Disable memory pattern optimisation — saves ~30 MB RAM on MiniLM
        # with negligible impact on throughput for fixed-size batches.
        sess_options.enable_mem_pattern = False

        self._onnx_session = ort.InferenceSession(
            str(model_path),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )

        # Use lightweight tokenizers library (not transformers)
        self._tokenizer = Tokenizer.from_pretrained(_ONNX_MODEL_REPO)
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self._tokenizer.enable_truncation(max_length=256)
        self._dimension = _ONNX_DIMENSION
        self._backend = "onnx"

    def _load_sentence_transformers(self) -> None:
        """Load the sentence-transformers model (heavier, fallback)."""
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformers model: %s", self.model_name)
        self._model = SentenceTransformer(self.model_name)
        self._dimension = self._model.get_sentence_embedding_dimension()
        self._backend = "sentence_transformers"

    def _touch(self) -> None:
        """Record model usage and reset the auto-unload timer."""
        self._last_used = time.monotonic()
        self._schedule_unload()

    def _schedule_unload(self) -> None:
        """Schedule auto-unload after idle_timeout seconds."""
        if self._unload_timer is not None:
            self._unload_timer.cancel()
        if self.idle_timeout > 0:
            self._unload_timer = threading.Timer(self.idle_timeout, self._maybe_unload)
            self._unload_timer.daemon = True
            self._unload_timer.start()

    def _maybe_unload(self) -> None:
        """Unload the model if it has been idle long enough."""
        if not self.is_loaded:
            return
        elapsed = time.monotonic() - self._last_used
        if elapsed >= self.idle_timeout:
            logger.info(
                "Model idle for %.0fs (threshold %.0fs), unloading to free memory",
                elapsed, self.idle_timeout,
            )
            self.cooldown()

    def warmup(self) -> None:
        """Eagerly load the model and run a dummy embedding to warm up."""
        t0 = time.perf_counter()
        _ = self.embed(["warmup"])
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("Embedder warmup complete in %.0fms", elapsed)

    def cooldown(self) -> None:
        """Explicitly unload the model to free memory."""
        with self._lock:
            if not self.is_loaded:
                return

            self._model = None
            self._onnx_session = None
            self._tokenizer = None
            gc.collect()

            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            logger.info("Embedding model unloaded (%s backend), memory freed", self._backend)

        # Clear the query cache — embeddings from the old session are still
        # valid (same model), but clearing avoids memory accumulation when the
        # model cycles through idle/active phases.
        with self._query_cache_lock:
            self._query_cache.clear()

        # Clear chunk cache too (same reasoning)
        with self._chunk_cache_lock:
            self._chunk_cache.clear()

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    @property
    def dimension(self) -> int:
        """Return the effective embedding dimension (after Matryoshka truncation)."""
        if self._dimension is not None:
            return min(self._target_dim, self._dimension)
        self._ensure_loaded()
        return min(self._target_dim, self._dimension)

    def _truncate_and_normalize(self, embeddings: np.ndarray) -> np.ndarray:
        """Truncate to target dimension and re-normalize (Matryoshka).

        When target_dim < model dimension, keeps only the first N dimensions
        then L2-normalizes. This preserves ranking quality per the Matryoshka
        representation learning principle.
        """
        if self._target_dim >= embeddings.shape[1]:
            return embeddings
        truncated = embeddings[:, :self._target_dim]
        norms = np.linalg.norm(truncated, axis=1, keepdims=True)
        norms = np.clip(norms, a_min=1e-9, a_max=None)
        return (truncated / norms).astype(np.float32)

    def _mean_pool_and_normalize(
        self, token_embeddings: np.ndarray, attention_mask: np.ndarray
    ) -> np.ndarray:
        """Mean pooling over token embeddings, then L2-normalize."""
        # token_embeddings: (batch, seq_len, hidden)
        # attention_mask: (batch, seq_len)
        mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
        summed = np.sum(token_embeddings * mask_expanded, axis=1)
        counts = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        pooled = summed / counts
        # L2 normalize
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms = np.clip(norms, a_min=1e-9, a_max=None)
        return (pooled / norms).astype(np.float32)

    def _embed_onnx(self, texts: list[str], batch_size: int) -> np.ndarray:
        """Embed using ONNX Runtime with lightweight tokenizers."""
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            encoded = self._tokenizer.encode_batch(batch)

            input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
            attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
            token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

            feeds = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            }

            outputs = self._onnx_session.run(None, feeds)
            # outputs[0] is token_embeddings (batch, seq_len, hidden)
            token_embeddings = outputs[0]
            pooled = self._mean_pool_and_normalize(
                token_embeddings, attention_mask.astype(np.float32)
            )
            all_embeddings.append(pooled)

        return np.vstack(all_embeddings)

    def _embed_sentence_transformers(self, texts: list[str], batch_size: int) -> np.ndarray:
        """Embed using sentence-transformers."""
        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return embeddings.astype(np.float32)

    def embed(self, texts: list[str], batch_size: int = 128) -> np.ndarray:
        """Embed a list of text strings.

        Applies Matryoshka dimension truncation when target_dim < model dim.

        Args:
            texts: List of text strings to embed.
            batch_size: Number of texts to embed at once.

        Returns:
            numpy array of shape (len(texts), dimension).
        """
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, self.dimension)

        self._ensure_loaded()

        if self._backend == "onnx":
            full = self._embed_onnx(texts, batch_size)
        else:
            full = self._embed_sentence_transformers(texts, batch_size)

        return self._truncate_and_normalize(full)

    def embed_with_cache(
        self,
        texts: list[str],
        batch_size: int = 128,
        keys: Optional[list[str]] = None,
    ) -> np.ndarray:
        """Embed texts with chunk-level LRU caching.

        Identical chunks that were embedded in a previous call (or a previous
        indexing run in this session) are returned from cache without hitting
        ONNX inference.  This accelerates re-indexing of files with minor edits
        where most chunks are unchanged.

        Args:
            texts: List of text strings to embed.
            batch_size: ONNX inner batch size for uncached texts.
            keys: Optional pre-computed SHA-256 hex digests (one per text).
                  When omitted, SHA-256 of each text is computed here.

        Returns:
            numpy array of shape (len(texts), dimension).
        """
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, self.dimension)

        dim = self.dimension  # ensures model loaded

        # Compute cache keys
        if keys is None:
            keys = [hashlib.sha256(t.encode("utf-8", errors="replace")).hexdigest() for t in texts]

        result = np.empty((len(texts), dim), dtype=np.float32)
        miss_indices: list[int] = []
        miss_texts: list[str] = []

        with self._chunk_cache_lock:
            for i, (text, key) in enumerate(zip(texts, keys)):
                if key in self._chunk_cache:
                    result[i] = self._chunk_cache[key]
                    self._chunk_cache.move_to_end(key)
                    self._chunk_cache_hits += 1
                else:
                    miss_indices.append(i)
                    miss_texts.append(text)
                    self._chunk_cache_misses += 1

        if miss_texts:
            miss_embeddings = self.embed(miss_texts, batch_size=batch_size)
            with self._chunk_cache_lock:
                for local_i, (global_i, key) in enumerate(zip(miss_indices, [keys[j] for j in miss_indices])):
                    emb = miss_embeddings[local_i]
                    result[global_i] = emb
                    self._chunk_cache[key] = emb
                    self._chunk_cache.move_to_end(key)
                    # Evict oldest entries when over capacity
                    while len(self._chunk_cache) > self._CHUNK_CACHE_SIZE:
                        self._chunk_cache.popitem(last=False)

        return result

    @property
    def chunk_cache_stats(self) -> dict:
        """Return chunk cache hit/miss statistics."""
        total = self._chunk_cache_hits + self._chunk_cache_misses
        hit_rate = self._chunk_cache_hits / total if total else 0.0
        return {
            "hits": self._chunk_cache_hits,
            "misses": self._chunk_cache_misses,
            "hit_rate": hit_rate,
            "size": len(self._chunk_cache),
        }

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string, with LRU caching for repeated queries.

        Repeated identical queries (e.g. paginated searches, retries) return
        the cached embedding directly — no ONNX inference needed.

        Returns:
            1D numpy array of shape (dimension,).
        """
        # Fast path: return cached embedding if available.
        with self._query_cache_lock:
            if query in self._query_cache:
                self._query_cache.move_to_end(query)
                return self._query_cache[query].copy()

        # Slow path: compute embedding, then cache it.
        result = self.embed([query])[0]

        with self._query_cache_lock:
            self._query_cache[query] = result
            self._query_cache.move_to_end(query)
            # Evict oldest entry if over capacity.
            while len(self._query_cache) > self._QUERY_CACHE_SIZE:
                self._query_cache.popitem(last=False)

        return result.copy()
