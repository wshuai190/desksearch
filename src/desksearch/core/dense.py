"""Dense vector index using FAISS for cosine-similarity search.

Supports two index types:
- IndexFlatIP for small collections (<50k vectors): exact search, simple.
- IndexIVFFlat for large collections (>=50k vectors): clustered search, lower memory.
Also supports memory-mapped indexes for reduced RSS.

Thread-safety: a ``threading.Lock`` serialises all FAISS operations.
FAISS does not guarantee thread safety on its own; the lock ensures that
simultaneous index/search calls from the pipeline thread-pool and async
API handlers cannot corrupt the in-memory index state.

Graceful degradation: if the on-disk index is corrupted or fails to load,
``DenseIndex`` creates a fresh empty index rather than crashing.  Callers
can check ``self.available`` to know whether the index loaded successfully.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# FAISS is imported lazily so module-level import errors are caught early.
try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError as exc:  # pragma: no cover
    _FAISS_AVAILABLE = False
    logger.error(
        "faiss-cpu is not installed — dense search will be unavailable. "
        "Install with: pip install faiss-cpu"
    )

# Threshold for switching from flat to IVF index.
IVF_THRESHOLD = 50_000
# Number of Voronoi cells for IVF (sqrt of expected dataset size is a good rule).
IVF_NLIST = 256
# Number of cells to probe at search time (higher = better recall, slower).
IVF_NPROBE = 16


class DenseIndex:
    """FAISS-backed dense vector index with cosine similarity search.

    Stores float32 embeddings and maps integer FAISS ids to string doc_ids.
    Persists both the FAISS index and the id mapping to disk.

    For collections >= IVF_THRESHOLD vectors the index is automatically
    built as an IVF index (IndexIVFFlat) which clusters vectors and only
    searches relevant clusters — much less memory for large collections.
    """

    def __init__(
        self,
        data_dir: Path,
        dimension: int = 384,
        *,
        use_mmap: bool = False,
    ) -> None:
        self._data_dir = data_dir / "dense"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._dimension = dimension
        self._use_mmap = use_mmap
        self._index_path = self._data_dir / "faiss.index"
        self._mapping_path = self._data_dir / "id_mapping.json"

        # doc_id <-> sequential int id
        self._doc_id_to_int: dict[str, int] = {}
        self._int_to_doc_id: dict[int, str] = {}
        self._next_id: int = 0

        # Serialise all FAISS operations to prevent race conditions.
        self._lock = threading.Lock()

        # ``available`` is False when FAISS is not installed or the index
        # file is irrecoverably corrupt.  Callers fall back to BM25-only.
        self.available: bool = _FAISS_AVAILABLE
        if self.available:
            self._index: Optional[faiss.Index] = self._load_or_create()
        else:
            self._index = None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_or_create(self) -> faiss.Index:
        if self._index_path.exists() and self._mapping_path.exists():
            try:
                if self._use_mmap:
                    index = faiss.read_index(
                        str(self._index_path), faiss.IO_FLAG_MMAP
                    )
                    logger.info("Loaded dense index (mmap) with %d vectors", index.ntotal)
                else:
                    index = faiss.read_index(str(self._index_path))
                    logger.info("Loaded dense index with %d vectors", index.ntotal)

                with open(self._mapping_path) as f:
                    mapping = json.load(f)
                self._doc_id_to_int = {k: int(v) for k, v in mapping["doc_to_int"].items()}
                self._int_to_doc_id = {int(k): v for k, v in mapping["int_to_doc"].items()}
                self._next_id = mapping.get("next_id", len(self._doc_id_to_int))
                return index
            except Exception as exc:
                logger.warning(
                    "Failed to load dense index (corrupt file?), creating a fresh one. "
                    "Error: %s",
                    exc,
                    exc_info=True,
                )
                # Remove corrupt files so we don't keep failing
                for p in (self._index_path, self._mapping_path):
                    try:
                        p.unlink(missing_ok=True)
                    except OSError:
                        pass

        return self._create_flat_index()

    def _create_flat_index(self) -> faiss.IndexIDMap:
        """Create a new flat (exact) inner-product index."""
        inner = faiss.IndexFlatIP(self._dimension)
        return faiss.IndexIDMap(inner)

    def _create_ivf_index(self, training_vectors: np.ndarray) -> faiss.IndexIDMap:
        """Create an IVF index trained on the given vectors."""
        nlist = min(IVF_NLIST, max(1, len(training_vectors) // 40))
        quantizer = faiss.IndexFlatIP(self._dimension)
        ivf = faiss.IndexIVFFlat(quantizer, self._dimension, nlist, faiss.METRIC_INNER_PRODUCT)
        ivf.nprobe = IVF_NPROBE
        ivf.train(self._normalize(training_vectors))
        index = faiss.IndexIDMap(ivf)
        logger.info("Created IVF index with nlist=%d, nprobe=%d", nlist, IVF_NPROBE)
        return index

    def maybe_rebuild_ivf(self) -> bool:
        """Rebuild the index as IVF if it has grown past the threshold.

        Returns True if a rebuild happened.
        """
        if not self.available or self._index is None:
            return False
        with self._lock:
            if self._index.ntotal < IVF_THRESHOLD:
                return False

            # Check if already IVF (unwrap IndexIDMap to inspect inner index)
            inner = faiss.downcast_index(self._index.index) if hasattr(self._index, 'index') else self._index
            if isinstance(inner, faiss.IndexIVFFlat):
                return False

            logger.info(
                "Index has %d vectors (>= %d threshold), rebuilding as IVF",
                self._index.ntotal, IVF_THRESHOLD,
            )

            # Extract all vectors and ids
            all_vectors = self._reconstruct_all_locked()
            if all_vectors is None or len(all_vectors) == 0:
                return False

            int_ids = np.array(list(self._int_to_doc_id.keys()), dtype=np.int64)
            new_index = self._create_ivf_index(all_vectors)
            new_index.add_with_ids(self._normalize(all_vectors), int_ids)
            self._index = new_index
            self._save_locked()
            return True

    def _reconstruct_all_locked(self) -> Optional[np.ndarray]:
        """Reconstruct all vectors — must be called while ``_lock`` is held."""
        n = self._index.ntotal
        if n == 0:
            return None
        try:
            vectors = np.zeros((n, self._dimension), dtype=np.float32)
            int_ids = sorted(self._int_to_doc_id.keys())
            for i, int_id in enumerate(int_ids):
                vectors[i] = self._index.reconstruct(int_id)
            return vectors
        except Exception:
            logger.warning("Could not reconstruct vectors for IVF rebuild")
            return None

    def save(self) -> None:
        """Persist the FAISS index and id mapping to disk."""
        with self._lock:
            self._save_locked()

    def _save_locked(self) -> None:
        """Persist to disk — must be called while ``_lock`` is held."""
        if not self.available or self._index is None:
            return
        try:
            faiss.write_index(self._index, str(self._index_path))
            mapping = {
                "doc_to_int": self._doc_id_to_int,
                "int_to_doc": {str(k): v for k, v in self._int_to_doc_id.items()},
                "next_id": self._next_id,
            }
            with open(self._mapping_path, "w") as f:
                json.dump(mapping, f)
        except Exception as exc:
            logger.error("Failed to persist FAISS index: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        """L2-normalize vectors so inner product == cosine similarity."""
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-10)
        return vectors / norms

    def add(self, doc_id: str, embedding: np.ndarray) -> None:
        """Add a single document embedding. Replaces if doc_id exists."""
        self.add_batch([(doc_id, embedding)])

    def add_batch(self, items: list[tuple[str, np.ndarray]]) -> None:
        """Add multiple (doc_id, embedding) pairs. Replaces existing doc_ids."""
        if not items or not self.available or self._index is None:
            return

        with self._lock:
            # Remove existing entries for these doc_ids
            ids_to_remove = []
            for doc_id, _ in items:
                if doc_id in self._doc_id_to_int:
                    ids_to_remove.append(self._doc_id_to_int[doc_id])

            if ids_to_remove:
                self._index.remove_ids(np.array(ids_to_remove, dtype=np.int64))
                for int_id in ids_to_remove:
                    old_doc_id = self._int_to_doc_id.pop(int_id, None)
                    if old_doc_id:
                        self._doc_id_to_int.pop(old_doc_id, None)

            # Build new vectors and ids
            vectors = np.array([emb for _, emb in items], dtype=np.float32)
            vectors = self._normalize(vectors)

            int_ids = []
            for doc_id, _ in items:
                int_id = self._next_id
                self._next_id += 1
                self._doc_id_to_int[doc_id] = int_id
                self._int_to_doc_id[int_id] = doc_id
                int_ids.append(int_id)

            id_array = np.array(int_ids, dtype=np.int64)
            self._index.add_with_ids(vectors, id_array)
            self._save_locked()

    def delete(self, doc_id: str) -> None:
        """Remove a document from the index."""
        if not self.available or self._index is None:
            return
        with self._lock:
            int_id = self._doc_id_to_int.pop(doc_id, None)
            if int_id is None:
                return
            self._int_to_doc_id.pop(int_id, None)
            self._index.remove_ids(np.array([int_id], dtype=np.int64))
            self._save_locked()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query_embedding: np.ndarray, top_k: int = 10) -> list[tuple[str, float]]:
        """Search by cosine similarity, returning (doc_id, score) pairs.

        Returns an empty list (rather than raising) if the index is
        unavailable or empty.  Scores are cosine similarities in [-1, 1].
        """
        if not self.available or self._index is None:
            return []

        with self._lock:
            if self._index.ntotal == 0:
                return []

            query = np.array([query_embedding], dtype=np.float32)
            query = self._normalize(query)

            k = min(top_k, self._index.ntotal)
            try:
                scores, ids = self._index.search(query, k)
            except Exception as exc:
                logger.error("FAISS search failed: %s", exc, exc_info=True)
                return []

            results: list[tuple[str, float]] = []
            for score, int_id in zip(scores[0], ids[0]):
                if int_id == -1:
                    continue
                doc_id = self._int_to_doc_id.get(int(int_id))
                if doc_id is not None:
                    results.append((doc_id, float(score)))

        return results

    @property
    def doc_count(self) -> int:
        """Number of vectors in the index."""
        if not self.available or self._index is None:
            return 0
        return self._index.ntotal

    @property
    def index_type(self) -> str:
        """Return a human-readable description of the current index type."""
        if not self.available or self._index is None:
            return "unavailable"
        inner = getattr(self._index, 'index', self._index)
        if isinstance(inner, faiss.IndexIVFFlat):
            return f"IVF (nlist={inner.nlist}, nprobe={inner.nprobe})"
        return "Flat (exact)"
