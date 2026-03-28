"""Embedding engine using Starbucks 2D Matryoshka model (ielabgroup/Starbucks-msmarco).

Supports three speed tiers via layer × dimension truncation:
  - fast:    2 layers, 32d  (~3x faster than full, tiny index)
  - middle:  4 layers, 64d  (balanced — default)
  - pro:     6 layers, 128d (near full-model quality)

Uses CLS token pooling (not mean pooling) — this is what Starbucks was trained with.
Loads only the needed layers via AutoConfig(num_hidden_layers=N) for real speedup.

Falls back to all-MiniLM-L6-v2 via ONNX if Starbucks model can't be loaded.
"""
import atexit
import gc
import hashlib
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional

import numpy as np

# Global registry for atexit cleanup (prevents segfault from torch/FAISS at exit)
_active_embedders: list["Embedder"] = []
_atexit_registered = False


def _cleanup_all_embedders():
    """Unload all active embedders before Python's module cleanup.
    
    This prevents segfaults from conflicting C++ destructors in torch/FAISS
    when Python shuts down and cleans up shared libraries in arbitrary order.
    """
    for emb in list(_active_embedders):
        try:
            with emb._lock:
                # Cancel any pending timer
                if emb._unload_timer is not None:
                    emb._unload_timer.cancel()
                    emb._unload_timer = None
                # Force delete model references
                emb._model = None
                emb._tokenizer = None
                emb._onnx_session = None
        except Exception:
            pass
    _active_embedders.clear()
    # Force garbage collection to clean up torch tensors before exit
    gc.collect()
    try:
        import torch
        if hasattr(torch, '_C') and hasattr(torch._C, '_cuda_clearCublasWorkspaces'):
            torch._C._cuda_clearCublasWorkspaces()
    except Exception:
        pass

from desksearch.config import DEFAULT_EMBEDDING_MODEL, STARBUCKS_TIERS

logger = logging.getLogger(__name__)

_DEFAULT_IDLE_TIMEOUT = 300  # 5 minutes

# Fallback ONNX model
_ONNX_MODEL_REPO = "sentence-transformers/all-MiniLM-L6-v2"
_ONNX_MODEL_FILE = "onnx/model.onnx"
_ONNX_DIMENSION = 384

# Local Starbucks ONNX model directory
_STARBUCKS_ONNX_DIR = Path.home() / ".desksearch" / "models"

# Mapping from tier name to ONNX filename (prefer INT8 for speed)
_STARBUCKS_ONNX_FILES = {
    "fast": "starbucks-fast-int8.onnx",
    "middle": "starbucks-middle-int8.onnx",
    "pro": "starbucks-pro-int8.onnx",
}

# Optimal ONNX batch sizes per tier (profiled on Apple M-series)
# middle-INT8: smaller batches are faster; fast-INT8: larger batches win
_STARBUCKS_ONNX_BATCH = {
    "fast": 128,
    "middle": 32,
    "pro": 32,
}


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
        global _atexit_registered
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

        # Register atexit cleanup to prevent segfaults from torch/FAISS at exit
        _active_embedders.append(self)
        if not _atexit_registered:
            atexit.register(_cleanup_all_embedders)
            _atexit_registered = True

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

            # Try Starbucks ONNX first (fastest — 6x over PyTorch)
            if self.model_name == DEFAULT_EMBEDDING_MODEL and _onnx_available():
                try:
                    self._load_starbucks_onnx()
                except Exception as e:
                    logger.warning("Failed to load Starbucks ONNX model: %s", e)
                    self._onnx_session = None
                    self._tokenizer = None

            # Fallback: Starbucks via PyTorch (slower but always works)
            if not self.is_loaded and self.model_name == DEFAULT_EMBEDDING_MODEL and _transformers_available():
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

    def _resolve_tier(self) -> str:
        """Return the Starbucks tier name matching target layers/dim."""
        for tier_name, (layers, dim) in STARBUCKS_TIERS.items():
            if layers == self._target_layers and dim == self._target_dim:
                return tier_name
        return "middle"

    def _auto_export_starbucks_onnx(self, tier: str, onnx_path: Path, tokenizer_path: Path) -> None:
        """Auto-export the Starbucks ONNX model for the given tier.

        Requires torch + transformers. Downloads the model once, saves a
        6-layer version locally, then exports the needed tier to ONNX.

        Runs the actual export in a subprocess to avoid torch/FAISS C++
        destructor conflicts that cause SIGSEGV on macOS.
        """
        import subprocess
        import sys

        layers, dim = STARBUCKS_TIERS[tier]
        logger.info(
            "Auto-exporting Starbucks ONNX model for tier '%s' (%d layers, %dd)...",
            tier, layers, dim,
        )

        # Ensure the 6-layer base model is downloaded (safe — no torch needed)
        local_model = self._ensure_local_model()

        _STARBUCKS_ONNX_DIR.mkdir(parents=True, exist_ok=True)

        # Run ONNX export in an isolated subprocess to prevent torch/FAISS
        # C++ destructor conflicts that cause SIGSEGV at exit on macOS.
        export_script = f'''
import sys, os, logging
logging.basicConfig(level=logging.INFO)
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import torch
import torch.nn as nn
from transformers import AutoModel, AutoConfig, AutoTokenizer

local_model = "{local_model}"
onnx_path = "{onnx_path}"
tokenizer_path = "{tokenizer_path}"
layers = {layers}
dim = {dim}

# Load model with truncated layers
config = AutoConfig.from_pretrained(local_model)
config.num_hidden_layers = layers

# Suppress transformers warnings about unused weights
import logging as _logging
_tf_logger = _logging.getLogger("transformers.modeling_utils")
_tf_logger.setLevel(_logging.ERROR)

model = AutoModel.from_pretrained(local_model, config=config).eval()

class TierModel(nn.Module):
    def __init__(self, bert, d):
        super().__init__()
        self.bert = bert
        self.d = d
    def forward(self, input_ids, attention_mask):
        out = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        return out.last_hidden_state[:, :, :self.d]

wrapped = TierModel(model, dim).eval()

dummy_ids = torch.ones(1, 32, dtype=torch.long)
dummy_mask = torch.ones(1, 32, dtype=torch.long)
torch.onnx.export(
    wrapped, (dummy_ids, dummy_mask), onnx_path,
    input_names=["input_ids", "attention_mask"],
    output_names=["last_hidden_state"],
    dynamic_axes={{
        "input_ids": {{0: "batch_size", 1: "sequence_length"}},
        "attention_mask": {{0: "batch_size", 1: "sequence_length"}},
        "last_hidden_state": {{0: "batch_size", 1: "sequence_length"}},
    }},
    opset_version=14, do_constant_folding=True,
)
print("ONNX_EXPORT_OK")

# INT8 quantization
try:
    from onnxruntime.quantization import quantize_dynamic, QuantType
    from pathlib import Path
    fp32 = onnx_path + ".fp32"
    os.rename(onnx_path, fp32)
    quantize_dynamic(fp32, onnx_path, weight_type=QuantType.QInt8)
    os.unlink(fp32)
    print("INT8_QUANTIZE_OK")
except Exception as e:
    print(f"INT8_SKIP: {{e}}")

# Save tokenizer
if not os.path.exists(tokenizer_path):
    tokenizer = AutoTokenizer.from_pretrained(local_model)
    tokenizer.save_pretrained("{_STARBUCKS_ONNX_DIR}")
    print("TOKENIZER_OK")

print("EXPORT_DONE")
'''
        result = subprocess.run(
            [sys.executable, "-c", export_script],
            capture_output=True, text=True, timeout=300,
        )

        if "EXPORT_DONE" not in result.stdout:
            # Log full output for debugging
            if result.stdout:
                logger.info("Export stdout: %s", result.stdout.strip())
            if result.stderr:
                # Filter out expected warnings
                stderr_lines = [
                    l for l in result.stderr.splitlines()
                    if "IS expected" not in l and "IS NOT expected" not in l
                    and "not used when initializing" not in l
                ]
                if stderr_lines:
                    logger.warning("Export stderr: %s", "\n".join(stderr_lines[:10]))
            raise RuntimeError(
                f"ONNX export subprocess failed (exit={result.returncode}). "
                f"Check logs above for details."
            )

        if not onnx_path.exists():
            raise FileNotFoundError(f"ONNX export completed but file not found: {onnx_path}")

        size_mb = onnx_path.stat().st_size / (1024 * 1024)
        logger.info("Exported %s (%.1f MB)", onnx_path.name, size_mb)

    def _load_starbucks_onnx(self) -> None:
        """Load Starbucks model via pre-exported ONNX (INT8) for maximum speed.

        These models were exported with CLS pooling and dimension truncation
        baked in, so the output is already the right shape.  INT8 quantisation
        gives ~6x speedup over PyTorch float32 on Apple M-series CPUs.

        If the ONNX file does not exist and torch+transformers are available,
        auto-exports it on first run.
        """
        import onnxruntime as ort
        from tokenizers import Tokenizer

        tier = self._resolve_tier()

        onnx_file = _STARBUCKS_ONNX_FILES.get(tier)
        if onnx_file is None:
            raise FileNotFoundError(f"No ONNX file mapping for tier '{tier}'")

        onnx_path = _STARBUCKS_ONNX_DIR / onnx_file
        tokenizer_path = _STARBUCKS_ONNX_DIR / "tokenizer.json"

        # Auto-export if ONNX file missing and torch is available
        if not onnx_path.exists() or not tokenizer_path.exists():
            if _transformers_available():
                self._auto_export_starbucks_onnx(tier, onnx_path, tokenizer_path)
            else:
                raise FileNotFoundError(
                    f"ONNX model not found: {onnx_path}\n"
                    f"Install torch + transformers to auto-export, or run: "
                    f"python -m desksearch.scripts.export_onnx"
                )

        if not onnx_path.exists():
            raise FileNotFoundError(f"ONNX model not found after export attempt: {onnx_path}")
        if not tokenizer_path.exists():
            raise FileNotFoundError(f"Tokenizer not found: {tokenizer_path}")

        logger.info(
            "Loading Starbucks ONNX model: %s (tier=%s, %d layers, %dd)",
            onnx_file, tier, self._target_layers, self._target_dim,
        )

        import os
        import platform
        ncpus = os.cpu_count() or 4
        is_apple = platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64")
        intra = min(4, ncpus) if is_apple else min(ncpus // 2, 8)

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = intra
        sess_options.inter_op_num_threads = 1
        sess_options.enable_mem_pattern = False

        self._onnx_session = ort.InferenceSession(
            str(onnx_path), sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self._tokenizer.enable_truncation(max_length=256)

        self._dimension = self._target_dim
        self._backend = "starbucks_onnx"
        self._onnx_optimal_batch = _STARBUCKS_ONNX_BATCH.get(tier, 32)
        logger.info(
            "Starbucks ONNX ready: %s, dim=%d, optimal_batch=%d",
            onnx_file, self._dimension, self._onnx_optimal_batch,
        )

    # Max layers we ever need — pre-cut the model to this on first download
    _MAX_LAYERS = 6

    def _get_local_model_path(self) -> Path:
        """Return path to the locally saved 6-layer Starbucks model."""
        return Path.home() / ".desksearch" / "models" / "starbucks-6layer"

    def _ensure_local_model(self) -> Path:
        """Download the full Starbucks model once, save a 6-layer version locally.

        Subsequent loads use the local 6-layer model — faster startup, less disk.
        The full 12-layer model is never kept; only layers 0-5 are saved.
        After saving, the full model is removed from HuggingFace cache.
        """
        from transformers import AutoTokenizer, AutoModel, AutoConfig

        local_path = self._get_local_model_path()

        if (local_path / "config.json").exists():
            self._log_model_size(local_path)
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
        config.save_pretrained(local_path)

        # Save tokenizer too
        tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        tokenizer.save_pretrained(local_path)

        logger.info("Saved 6-layer Starbucks model to %s", local_path)
        self._log_model_size(local_path)

        del model
        gc.collect()

        # Clean up full 12-layer model from HuggingFace cache
        self._cleanup_hf_cache()

        return local_path

    @staticmethod
    def _log_model_size(model_path: Path) -> None:
        """Log the on-disk size of the local model directory."""
        try:
            total = sum(f.stat().st_size for f in model_path.iterdir() if f.is_file())
            mb = total / (1024 * 1024)
            logger.info("Local 6-layer model size: %.1f MB (%s)", mb, model_path)
        except Exception:
            pass

    def _cleanup_hf_cache(self) -> None:
        """Remove the full Starbucks model from HuggingFace cache to save disk space."""
        import shutil
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub" / "models--ielabgroup--Starbucks-msmarco"
        if cache_dir.exists():
            try:
                size_mb = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file()) / (1024 * 1024)
                shutil.rmtree(cache_dir)
                logger.info("Cleaned up full model from HuggingFace cache (freed %.1f MB)", size_mb)
            except Exception as e:
                logger.warning("Failed to clean HuggingFace cache: %s", e)

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
        # Use ignore_mismatched_sizes to suppress UNEXPECTED key warnings
        # when loading fewer layers than saved in the checkpoint
        config = AutoConfig.from_pretrained(
            local_path,
            num_hidden_layers=self._target_layers,
        )
        import logging as _logging
        # Temporarily suppress transformers model loading warnings
        _tf_logger = _logging.getLogger("transformers.modeling_utils")
        _prev_level = _tf_logger.level
        _tf_logger.setLevel(_logging.ERROR)
        self._model = AutoModel.from_pretrained(
            local_path, config=config
        ).eval()
        _tf_logger.setLevel(_prev_level)

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

    def _embed_starbucks_onnx(self, texts: list[str], batch_size: int) -> np.ndarray:
        """Embed using Starbucks ONNX model — CLS token from last_hidden_state."""
        # Use profiled optimal batch size unless caller overrides with something smaller
        bs = min(batch_size, getattr(self, '_onnx_optimal_batch', batch_size))

        all_embeddings = []
        for i in range(0, len(texts), bs):
            batch = texts[i : i + bs]
            encoded = self._tokenizer.encode_batch(batch)

            input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
            attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)

            outputs = self._onnx_session.run(None, {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            })

            # CLS token is at position 0 of last_hidden_state
            cls_embeddings = outputs[0][:, 0, :]

            # L2 normalize
            norms = np.clip(np.linalg.norm(cls_embeddings, axis=1, keepdims=True), 1e-9, None)
            all_embeddings.append((cls_embeddings / norms).astype(np.float32))

        return np.vstack(all_embeddings)

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

        if self._backend == "starbucks_onnx":
            return self._embed_starbucks_onnx(texts, batch_size)
        elif self._backend == "starbucks":
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
