"""Embedding engine using Starbucks 2D Matryoshka model (ielabgroup/Starbucks-msmarco).

Supports three speed tiers via layer × dimension truncation:
  - fast:    2 layers, 32d  (~3x faster than full, tiny index)
  - regular: 4 layers, 64d  (balanced — default)
  - pro:     6 layers, 128d (near full-model quality)

Uses CLS token pooling (not mean pooling) — this is what Starbucks was trained with.
Loads only the needed layers via AutoConfig(num_hidden_layers=N) for real speedup.

Falls back to all-MiniLM-L6-v2 via ONNX if Starbucks model can't be loaded.
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

from desksearch.config import DEFAULT_EMBEDDING_MODEL, STARBUCKS_TIERS

logger = logging.getLogger(__name__)

_DEFAULT_IDLE_TIMEOUT = 300  # 5 minutes

# Fallback ONNX model
_ONNX_MODEL_REPO = "sentence-transformers/all-MiniLM-L6-v2"
_ONNX_MODEL_FILE = "onnx/model.onnx"
_ONNX_DIMENSION = 384


def _onnx_available() -> bool:
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def _transformers_available() -> bool:
    try:
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def _sentence_transformers_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


class Embedder:
    """Embedding engine with Starbucks 2D Matryoshka support.

    Primary: loads Starbucks model with truncated layers for real inference speedup.
    Fallback: ONNX MiniLM with dimension truncation.
    """

    _QUERY_CACHE_SIZE = 512
    _CHUNK_CACHE_SIZE = 8192

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        idle_timeout: float = _DEFAULT_IDLE_TIMEOUT,
        embedding_dim: int = 64,
        embedding_layers: int = 4,
    ) -> None:
        self.model_name = model_name
        self.idle_timeout = idle_timeout
        self._target_dim = embedding_dim
        self._target_layers = embedding_layers

        self._model = None              # transformers AutoModel
        self._tokenizer = None          # transformers AutoTokenizer or tokenizers.Tokenizer
        self._onnx_session = None       # ONNX fallback
        self._backend: Optional[str] = None  # "starbucks", "onnx", or "sentence_transformers"
        self._lock = threading.Lock()
        self._last_used: float = 0.0
        self._unload_timer: Optional[threading.Timer] = None
        self._dimension: Optional[int] = None

        # LRU caches
        self._query_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._query_cache_lock = threading.Lock()
        self._chunk_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._chunk_cache_lock = threading.Lock()
        self._chunk_cache_hits: int = 0
        self._chunk_cache_misses: int = 0

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        return self._model is not None or self._onnx_session is not None

    @property
    def backend(self) -> Optional[str]:
        return self._backend

    def _ensure_loaded(self):
        if self._model is not None or self._onnx_session is not None:
            self._touch()
            return

        with self._lock:
            if self._model is not None or self._onnx_session is not None:
                self._touch()
                return

            t0 = time.perf_counter()

            # Try Starbucks first (preferred)
            if self.model_name == DEFAULT_EMBEDDING_MODEL and _transformers_available():
                try:
                    self._load_starbucks()
                except Exception as e:
                    logger.warning("Failed to load Starbucks model, falling back: %s", e)
                    self._model = None
                    self._tokenizer = None

            # Fallback to ONNX MiniLM
            if not self.is_loaded and _onnx_available():
                self._load_onnx()

            # Last resort: sentence-transformers
            if not self.is_loaded and _sentence_transformers_available():
                self._load_sentence_transformers()

            if not self.is_loaded:
                raise RuntimeError(
                    "No embedding backend available. Install transformers "
                    "(for Starbucks model) or onnxruntime (for MiniLM fallback)."
                )

            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                "Embedder loaded in %.0fms via %s (layers=%s, dim=%d)",
                elapsed, self._backend, self._target_layers, self._dimension,
            )
            self._touch()

    # Max layers we ever need — pre-cut the model to this on first download
    _MAX_LAYERS = 6

    def _get_local_model_path(self) -> Path:
        """Return path to the locally saved 6-layer Starbucks model."""
        return Path.home() / ".desksearch" / "models" / "starbucks-6layer"

    def _ensure_local_model(self) -> Path:
        """Download the full Starbucks model once, save a 6-layer version locally.

        Subsequent loads use the local 6-layer model — faster startup, less disk.
        The full 12-layer model is never kept; only layers 0-5 are saved.
        """
        from transformers import AutoTokenizer, AutoModel, AutoConfig

        local_path = self._get_local_model_path()

        if (local_path / "config.json").exists():
            return local_path

        logger.info("First-time setup: downloading Starbucks model and saving 6-layer version...")
        local_path.mkdir(parents=True, exist_ok=True)

        # Download full model, then save only 6 layers
        config = AutoConfig.from_pretrained(
            self.model_name,
            num_hidden_layers=self._MAX_LAYERS,
        )
        model = AutoModel.from_pretrained(self.model_name, config=config)
        model.save_pretrained(local_path)

        # Save tokenizer too
        tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        tokenizer.save_pretrained(local_path)

        logger.info("Saved 6-layer Starbucks model to %s", local_path)
        del model
        import gc; gc.collect()

        return local_path

    def _load_starbucks(self) -> None:
        """Load Starbucks model with truncated layers for real speedup.

        Uses locally saved 6-layer model. If user picks 'fast' (2 layers),
        only 2 layers are loaded — real compute savings via AutoConfig.
        """
        import torch
        from transformers import AutoTokenizer, AutoModel, AutoConfig

        # Ensure we have the 6-layer model saved locally
        local_path = self._ensure_local_model()

        logger.info(
            "Loading Starbucks model: %d of 6 layers, %dd output",
            self._target_layers, self._target_dim,
        )

        self._tokenizer = AutoTokenizer.from_pretrained(local_path)

        # Load only the layers we need (2, 4, or 6)
        config = AutoConfig.from_pretrained(
            local_path,
            num_hidden_layers=self._target_layers,
        )
        self._model = AutoModel.from_pretrained(
            local_path, config=config
        ).eval()

        # Disable gradients for inference
        for param in self._model.parameters():
            param.requires_grad = False

        self._dimension = self._target_dim
        self._backend = "starbucks"

        n_layers = len(self._model.encoder.layer)
        logger.info("Starbucks model ready: %d layers, %dd embeddings", n_layers, self._target_dim)

    def _get_onnx_model_path(self) -> Path:
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise RuntimeError(
                "huggingface_hub is required for ONNX model. pip install huggingface-hub"
            ) from exc
        return Path(hf_hub_download(repo_id=_ONNX_MODEL_REPO, filename=_ONNX_MODEL_FILE))

    def _load_onnx(self) -> None:
        """Load ONNX MiniLM fallback with dimension truncation."""
        import onnxruntime as ort
        from tokenizers import Tokenizer

        logger.info("Loading ONNX fallback: %s (dim truncated to %d)", _ONNX_MODEL_REPO, self._target_dim)

        model_path = self._get_onnx_model_path()

        import os, platform
        ncpus = os.cpu_count() or 4
        is_apple = platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64")
        intra = min(4, ncpus) if is_apple else min(ncpus // 2, 8)

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = intra
        sess_options.inter_op_num_threads = 1
        sess_options.enable_mem_pattern = False

        self._onnx_session = ort.InferenceSession(
            str(model_path), sess_options=sess_options, providers=["CPUExecutionProvider"],
        )
        self._tokenizer = Tokenizer.from_pretrained(_ONNX_MODEL_REPO)
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self._tokenizer.enable_truncation(max_length=256)
        self._dimension = min(self._target_dim, _ONNX_DIMENSION)
        self._backend = "onnx"

    def _load_sentence_transformers(self) -> None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading sentence-transformers fallback: all-MiniLM-L6-v2")
        self._model = SentenceTransformer("all-MiniLM-L6-v2")
        self._dimension = min(self._target_dim, self._model.get_sentence_embedding_dimension())
        self._backend = "sentence_transformers"

    def _touch(self) -> None:
        self._last_used = time.monotonic()
        self._schedule_unload()

    def _schedule_unload(self) -> None:
        if self._unload_timer is not None:
            self._unload_timer.cancel()
        if self.idle_timeout > 0:
            self._unload_timer = threading.Timer(self.idle_timeout, self._maybe_unload)
            self._unload_timer.daemon = True
            self._unload_timer.start()

    def _maybe_unload(self) -> None:
        if not self.is_loaded:
            return
        if time.monotonic() - self._last_used >= self.idle_timeout:
            logger.info("Model idle for %.0fs, unloading", self.idle_timeout)
            self.cooldown()

    def warmup(self) -> None:
        t0 = time.perf_counter()
        _ = self.embed(["warmup"])
        logger.info("Embedder warmup in %.0fms", (time.perf_counter() - t0) * 1000)

    def cooldown(self) -> None:
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
            logger.info("Embedding model unloaded (%s)", self._backend)
        with self._query_cache_lock:
            self._query_cache.clear()
        with self._chunk_cache_lock:
            self._chunk_cache.clear()

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    @property
    def dimension(self) -> int:
        if self._dimension is not None:
            return self._dimension
        self._ensure_loaded()
        return self._dimension

    def _embed_starbucks(self, texts: list[str], batch_size: int) -> np.ndarray:
        """Embed using Starbucks model — CLS token, truncated dimensions."""
        import torch

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            inputs = self._tokenizer(
                batch, return_tensors="pt", padding=True,
                truncation=True, max_length=256,
            )

            with torch.no_grad():
                outputs = self._model(**inputs, return_dict=True)

            # CLS token embedding, truncated to target dimensions
            cls_embeddings = outputs.last_hidden_state[:, 0, :self._target_dim]
            all_embeddings.append(cls_embeddings.cpu().numpy().astype(np.float32))

        return np.vstack(all_embeddings)

    def _embed_onnx(self, texts: list[str], batch_size: int) -> np.ndarray:
        """Embed using ONNX MiniLM with mean pooling + dimension truncation."""
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            encoded = self._tokenizer.encode_batch(batch)

            input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
            attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
            token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

            outputs = self._onnx_session.run(None, {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            })

            token_embs = outputs[0]
            mask_exp = attention_mask[:, :, np.newaxis].astype(np.float32)
            pooled = np.sum(token_embs * mask_exp, axis=1) / np.clip(mask_exp.sum(axis=1), 1e-9, None)

            # Truncate to target dim
            if pooled.shape[1] > self._target_dim:
                pooled = pooled[:, :self._target_dim]

            # L2 normalize
            norms = np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9, None)
            all_embeddings.append((pooled / norms).astype(np.float32))

        return np.vstack(all_embeddings)

    def _embed_sentence_transformers(self, texts: list[str], batch_size: int) -> np.ndarray:
        embs = self._model.encode(
            texts, batch_size=batch_size, show_progress_bar=False,
            convert_to_numpy=True, normalize_embeddings=True,
        ).astype(np.float32)
        if embs.shape[1] > self._target_dim:
            embs = embs[:, :self._target_dim]
            norms = np.clip(np.linalg.norm(embs, axis=1, keepdims=True), 1e-9, None)
            embs = embs / norms
        return embs

    def embed(self, texts: list[str], batch_size: int = 128) -> np.ndarray:
        """Embed a list of texts. Returns (N, dimension) float32 array."""
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, self.dimension)

        self._ensure_loaded()

        if self._backend == "starbucks":
            return self._embed_starbucks(texts, batch_size)
        elif self._backend == "onnx":
            return self._embed_onnx(texts, batch_size)
        else:
            return self._embed_sentence_transformers(texts, batch_size)

    def embed_with_cache(
        self, texts: list[str], batch_size: int = 128, keys: Optional[list[str]] = None,
    ) -> np.ndarray:
        """Embed with chunk-level LRU cache. Cache hits skip inference."""
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, self.dimension)

        dim = self.dimension
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
            miss_embs = self.embed(miss_texts, batch_size=batch_size)
            with self._chunk_cache_lock:
                for local_i, global_i in enumerate(miss_indices):
                    key = keys[global_i]
                    emb = miss_embs[local_i]
                    result[global_i] = emb
                    self._chunk_cache[key] = emb
                    self._chunk_cache.move_to_end(key)
                    while len(self._chunk_cache) > self._CHUNK_CACHE_SIZE:
                        self._chunk_cache.popitem(last=False)

        return result

    @property
    def chunk_cache_stats(self) -> dict:
        total = self._chunk_cache_hits + self._chunk_cache_misses
        return {
            "hits": self._chunk_cache_hits,
            "misses": self._chunk_cache_misses,
            "hit_rate": self._chunk_cache_hits / total if total else 0.0,
            "size": len(self._chunk_cache),
        }

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query with LRU cache. Returns 1D array."""
        with self._query_cache_lock:
            if query in self._query_cache:
                self._query_cache.move_to_end(query)
                return self._query_cache[query].copy()

        result = self.embed([query])[0]

        with self._query_cache_lock:
            self._query_cache[query] = result
            self._query_cache.move_to_end(query)
            while len(self._query_cache) > self._QUERY_CACHE_SIZE:
                self._query_cache.popitem(last=False)

        return result.copy()
