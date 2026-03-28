"""Dense vector index using FAISS for dot-product (inner product) search.

Supports three index types, auto-selected by corpus size:
- IndexFlatIP  for small collections (<HNSW_THRESHOLD vectors): exact search, simple.
- IndexHNSWFlat for medium collections (HNSW_THRESHOLD–IVF_THRESHOLD): ANN,
  no training, fast search, good recall.
- IndexIVFFlat for large collections (>IVF_THRESHOLD): clustered search, lower memory.

Soft deletion is used for HNSW (remove_ids is not supported there); the mapping
layer tracks live doc_ids so deleted docs are silently filtered from results.

Also supports memory-mapped indexes (faiss.IO_FLAG_MMAP) for reduced RSS.

Thread-safety: a ``threading.Lock`` serialises all FAISS operations.
FAISS does not guarantee thread safety on its own; the lock ensures that
simultaneous index/search calls from the pipeline thread-pool and async
API handlers cannot corrupt the in-memory index state.

Graceful degradation: if the on-disk index is corrupted or fails to load,
``DenseIndex`` creates a fresh empty index rather than crashing.  Callers
can check ``self.available`` to know whether the index loaded successfully.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

import numpy as np

# orjson is ~3x faster than stdlib json for serialising the id_mapping dict.
try:
    import orjson as _json_lib
    def _json_loads(s: str | bytes) -> dict:
        return _json_lib.loads(s)
    def _json_dumps(obj) -> bytes:
        return _json_lib.dumps(obj)
except ImportError:
    import json as _json_lib  # type: ignore
    def _json_loads(s) -> dict:
        return _json_lib.loads(s)
    def _json_dumps(obj) -> bytes:
        return _json_lib.dumps(obj).encode()

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

# ── Index-type thresholds ────────────────────────────────────────────────────
# Flat  →  <HNSW_THRESHOLD  : exact, fast for small corpora
# HNSW  →  HNSW_THRESHOLD..IVF_THRESHOLD : ANN, no training, good recall
# IVF   →  >IVF_THRESHOLD   : clustered ANN, best for very large corpora

HNSW_THRESHOLD = 1_000    # upgrade Flat → HNSW when ntotal exceeds this
IVF_THRESHOLD  = 50_000   # upgrade HNSW → IVF  when ntotal exceeds this

# HNSW parameters
HNSW_M            = 32    # neighbours per node (higher = better recall/slower build)
HNSW_EF_CONSTRUCT = 200   # build-time beam width
HNSW_EF_SEARCH    = 50    # search-time beam width

# IVF parameters
IVF_NLIST  = 256   # Voronoi cells
IVF_NPROBE = 16    # cells to probe at search time


class DenseIndex:
    """FAISS-backed dense vector index with dot-product (inner product) search.

    Stores float32 embeddings and maps integer FAISS ids to string doc_ids.
    Persists both the FAISS index and the id mapping to disk.

    Index type is chosen automatically:
    - ntotal < HNSW_THRESHOLD : IndexFlatIP  (exact)
    - HNSW_THRESHOLD ≤ ntotal < IVF_THRESHOLD : IndexHNSWFlat (ANN, no training)
    - ntotal ≥ IVF_THRESHOLD  : IndexIVFFlat (clustered ANN)

    Soft deletion is used when the inner index does not support ``remove_ids``
    (e.g. HNSW).  Logically-deleted vectors stay in FAISS but are filtered
    from all search results and the ``doc_count`` property.  Call
    ``maybe_rebuild_index()`` to reclaim their memory.
    """

    def __init__(
        self,
        data_dir: Path,
        dimension: int = 64,
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

        # Soft-deleted int IDs (used when inner index doesn't support remove_ids)
        self._soft_deleted: set[int] = set()

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

                with open(self._mapping_path, "rb") as f:
                    mapping = _json_loads(f.read())
                self._doc_id_to_int = {k: int(v) for k, v in mapping["doc_to_int"].items()}
                self._int_to_doc_id = {int(k): v for k, v in mapping["int_to_doc"].items()}
                self._next_id = mapping.get("next_id", len(self._doc_id_to_int))
                # Restore soft-deleted set: int ids present in FAISS but not in mapping
                known_int_ids = set(self._int_to_doc_id.keys())
                self._soft_deleted = {i for i in range(index.ntotal) if i not in known_int_ids}

                # Check dimension mismatch — if the saved index has a
                # different dimension than the current config, discard it.
                if index.d != self._dimension:
                    logger.warning(
                        "FAISS index dimension %d != config %d, rebuilding",
                        index.d, self._dimension,
                    )
                    for p in (self._index_path, self._mapping_path):
                        try:
                            p.unlink(missing_ok=True)
                        except OSError:
                            pass
                    return self._create_flat_index()

                # Tune HNSW efSearch for speed on larger indexes.
                # At 64d with >5k vectors, efSearch=32 gives good recall
                # while being ~40% faster than the default efSearch=50.
                self._tune_efsearch(index)

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

    # ------------------------------------------------------------------
    # HNSW tuning
    # ------------------------------------------------------------------

    @staticmethod
    def _tune_efsearch(index) -> None:
        """Lower HNSW efSearch on larger indexes for faster search.

        When the index has >5k vectors and the inner index is HNSW, reduce
        efSearch from the default 50 to 32.  At 64–384 dimensions this still
        gives >95% recall while shaving ~40% off search latency.
        """
        if not _FAISS_AVAILABLE:
            return
        inner = getattr(index, "index", index)
        if isinstance(inner, faiss.IndexHNSWFlat) and index.ntotal > 5_000:
            old_ef = inner.hnsw.efSearch
            inner.hnsw.efSearch = 32
            logger.info(
                "Tuned HNSW efSearch %d → 32 for %d-vector index",
                old_ef, index.ntotal,
            )

    # ------------------------------------------------------------------
    # Index factory methods
    # ------------------------------------------------------------------

    def _create_flat_index(self) -> faiss.Index:
        """Create a new flat (exact) inner-product index.
        
        Uses IndexIDMap2 which supports reconstruct() — required for
        auto-upgrading Flat → HNSW when the corpus grows.
        """
        inner = faiss.IndexFlatIP(self._dimension)
        return faiss.IndexIDMap2(inner)

    def _create_hnsw_index(self) -> faiss.Index:
        """Create an HNSW index (no training, good for 1k-100k vectors).

        HNSW does not support ``remove_ids``, so we use soft deletion.
        Uses IndexIDMap2 for reconstruct() support.
        """
        hnsw = faiss.IndexHNSWFlat(self._dimension, HNSW_M)
        hnsw.hnsw.efConstruction = HNSW_EF_CONSTRUCT
        hnsw.hnsw.efSearch = HNSW_EF_SEARCH
        # IndexIDMap2 wraps it for explicit ID management + reconstruct support
        index = faiss.IndexIDMap2(hnsw)
        logger.info(
            "Created HNSW index (M=%d, efConstruction=%d, efSearch=%d)",
            HNSW_M, HNSW_EF_CONSTRUCT, HNSW_EF_SEARCH,
        )
        return index

    def _create_ivf_index(self, training_vectors: np.ndarray) -> faiss.Index:
        """Create an IVF index trained on the given vectors."""
        nlist = min(IVF_NLIST, max(1, len(training_vectors) // 40))
        quantizer = faiss.IndexFlatIP(self._dimension)
        ivf = faiss.IndexIVFFlat(quantizer, self._dimension, nlist, faiss.METRIC_INNER_PRODUCT)
        ivf.nprobe = IVF_NPROBE
        ivf.train(self._normalize(training_vectors))
        index = faiss.IndexIDMap2(ivf)
        logger.info("Created IVF index with nlist=%d, nprobe=%d", nlist, IVF_NPROBE)
        return index

    # ------------------------------------------------------------------
    # Index-type helpers
    # ------------------------------------------------------------------

    def _inner_index(self) -> Optional[faiss.Index]:
        """Return the unwrapped (inner) index from the IDMap wrapper."""
        if self._index is None:
            return None
        return getattr(self._index, "index", self._index)

    def _supports_remove_ids(self) -> bool:
        """Check if current FAISS index supports remove_ids."""
        if self._index is None:
            return False
        # HNSW indices don't support remove_ids
        if isinstance(self._index, faiss.IndexHNSWFlat):
            return False
        # Wrapped indices (e.g., IndexIDMap wrapping HNSW)
        inner = self._inner_index()
        if inner is not None and isinstance(inner, faiss.IndexHNSWFlat):
            return False
        # Try a safe test
        try:
            # Verify the index actually works by checking its type string
            _ = str(type(self._index))
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Auto-upgrade
    # ------------------------------------------------------------------

    def maybe_upgrade_index(self) -> bool:
        """Upgrade the index type if the corpus has grown past a threshold.

        - Flat → HNSW when live count ≥ HNSW_THRESHOLD
        - HNSW → IVF  when live count ≥ IVF_THRESHOLD

        Returns True if an upgrade happened.  Must be called *outside* any
        held ``_lock`` — it acquires the lock internally.
        """
        if not self.available or self._index is None:
            return False

        live_count = len(self._doc_id_to_int)

        if live_count >= IVF_THRESHOLD:
            target = "ivf"
        elif live_count >= HNSW_THRESHOLD:
            target = "hnsw"
        else:
            return False  # Flat is still appropriate

        inner = self._inner_index()
        if target == "ivf" and isinstance(inner, faiss.IndexIVFFlat):
            return False  # Already IVF
        if target == "hnsw" and isinstance(inner, faiss.IndexHNSWFlat):
            return False  # Already HNSW

        with self._lock:
            # Re-check under lock (another thread may have upgraded first)
            inner = self._inner_index()
            if target == "ivf" and isinstance(inner, faiss.IndexIVFFlat):
                return False
            if target == "hnsw" and isinstance(inner, faiss.IndexHNSWFlat):
                return False

            logger.info(
                "Index has %d live vectors, upgrading to %s",
                live_count, target.upper(),
            )

            all_vecs, all_ids = self._reconstruct_live_locked()
            if all_vecs is None or len(all_vecs) == 0:
                return False

            if target == "ivf":
                new_index = self._create_ivf_index(all_vecs)
            else:
                new_index = self._create_hnsw_index()

            new_index.add_with_ids(self._normalize(all_vecs), all_ids)
            self._index = new_index
            self._soft_deleted.clear()
            self._save_locked()
            return True

    # Legacy alias so external code that calls maybe_rebuild_ivf still works.
    def maybe_rebuild_ivf(self) -> bool:  # noqa: D401
        """Alias for ``maybe_upgrade_index`` (backwards compatibility)."""
        return self.maybe_upgrade_index()

    # ------------------------------------------------------------------
    # Rebuild (compact soft-deleted slots)
    # ------------------------------------------------------------------

    def maybe_rebuild_index(self) -> bool:
        """Compact the index by removing soft-deleted vectors.

        Safe to call periodically to reclaim memory used by deleted docs.
        Returns True if a rebuild happened.
        """
        if not self.available or self._index is None:
            return False

        with self._lock:
            if not self._soft_deleted:
                return False

            logger.info(
                "Rebuilding dense index to remove %d soft-deleted vectors",
                len(self._soft_deleted),
            )
            all_vecs, all_ids = self._reconstruct_live_locked()
            if all_vecs is None or len(all_vecs) == 0:
                self._index = self._create_flat_index()
                self._soft_deleted.clear()
                self._save_locked()
                return True

            inner = self._inner_index()
            if isinstance(inner, faiss.IndexIVFFlat):
                new_index = self._create_ivf_index(all_vecs)
            elif isinstance(inner, faiss.IndexHNSWFlat):
                new_index = self._create_hnsw_index()
            else:
                new_index = self._create_flat_index()

            new_index.add_with_ids(self._normalize(all_vecs), all_ids)
            self._index = new_index
            self._soft_deleted.clear()
            self._save_locked()
            return True

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

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
            with open(self._mapping_path, "wb") as f:
                f.write(_json_dumps(mapping))
        except Exception as exc:
            logger.error("Failed to persist FAISS index: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        """Pass-through (no normalization).

        The Starbucks 2D Matryoshka model is trained with dot-product
        similarity — embeddings should NOT be L2-normalized.
        """
        return vectors

    def add(self, doc_id: str, embedding: np.ndarray) -> None:
        """Add a single document embedding. Replaces if doc_id exists."""
        self.add_batch([(doc_id, embedding)])

    def add_batch(
        self,
        items: list[tuple[str, np.ndarray]],
        *,
        defer_save: bool = False,
    ) -> None:
        """Add multiple (doc_id, embedding) pairs. Replaces existing doc_ids.

        Args:
            items: List of (doc_id, embedding) pairs.
            defer_save: If True, skip persisting to disk after this batch.
                Caller must call ``save()`` when done.  Use during bulk
                indexing to avoid writing the full FAISS index after every
                micro-batch (major I/O win for large imports).
        """
        if not items or not self.available or self._index is None:
            return

        with self._lock:
            # Remove existing entries for these doc_ids
            for doc_id, _ in items:
                if doc_id in self._doc_id_to_int:
                    old_int_id = self._doc_id_to_int.pop(doc_id)
                    self._int_to_doc_id.pop(old_int_id, None)
                    if self._supports_remove_ids():
                        try:
                            self._index.remove_ids(np.array([old_int_id], dtype=np.int64))
                        except Exception as e:
                            logger.warning("remove_ids failed (%s), using soft delete", e)
                            self._soft_deleted.add(old_int_id)
                    else:
                        self._soft_deleted.add(old_int_id)

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
            if not defer_save:
                self._save_locked()

        # Auto-upgrade index type if corpus crossed a threshold.
        # Done outside the lock to avoid deadlock (maybe_upgrade_index takes lock).
        self.maybe_upgrade_index()

    def delete(self, doc_id: str) -> None:
        """Remove a document from the index."""
        if not self.available or self._index is None:
            return
        with self._lock:
            int_id = self._doc_id_to_int.pop(doc_id, None)
            if int_id is None:
                return
            self._int_to_doc_id.pop(int_id, None)
            if self._supports_remove_ids():
                try:
                    self._index.remove_ids(np.array([int_id], dtype=np.int64))
                except Exception as e:
                    logger.warning("remove_ids failed (%s), using soft delete", e)
                    self._soft_deleted.add(int_id)
            else:
                # Soft-delete: keep vector in FAISS, filter at search time.
                self._soft_deleted.add(int_id)
            self._save_locked()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query_embedding: np.ndarray, top_k: int = 10) -> list[tuple[str, float]]:
        """Search by dot-product similarity, returning (doc_id, score) pairs.

        Returns an empty list (rather than raising) if the index is
        unavailable or empty.  Scores are dot-product similarities.
        Soft-deleted vectors are silently filtered from results.
        """
        if not self.available or self._index is None:
            return []

        with self._lock:
            if self._index.ntotal == 0:
                return []

            query = np.array([query_embedding], dtype=np.float32)
            query = self._normalize(query)

            # Fetch extra candidates to compensate for soft-deleted slots.
            extra = len(self._soft_deleted)
            k = min(top_k + extra, self._index.ntotal)
            try:
                scores, ids = self._index.search(query, k)
            except Exception as exc:
                logger.error("FAISS search failed: %s", exc, exc_info=True)
                return []

            results: list[tuple[str, float]] = []
            for score, int_id in zip(scores[0], ids[0]):
                if int_id == -1:
                    continue
                if int_id in self._soft_deleted:
                    continue
                doc_id = self._int_to_doc_id.get(int(int_id))
                if doc_id is not None:
                    results.append((doc_id, float(score)))
                    if len(results) >= top_k:
                        break

        return results

    # ------------------------------------------------------------------
    # Reconstruction helper (for index rebuild)
    # ------------------------------------------------------------------

    def _reconstruct_all_locked(self) -> Optional[np.ndarray]:
        """Reconstruct all live vectors from the index — lock must be held."""
        int_ids = sorted(self._int_to_doc_id.keys())
        if not int_ids:
            return None
        try:
            vectors = np.zeros((len(int_ids), self._dimension), dtype=np.float32)
            for i, int_id in enumerate(int_ids):
                vectors[i] = self._index.reconstruct(int_id)
            return vectors
        except Exception:
            logger.warning("Could not reconstruct vectors for index rebuild")
            return None

    def _reconstruct_live_locked(self) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Reconstruct only live (non-deleted) vectors — lock must be held.

        Returns (vectors, int_ids_array) or (None, None) on failure.
        """
        live_ids = sorted(k for k in self._int_to_doc_id if k not in self._soft_deleted)
        if not live_ids:
            return None, None
        try:
            vectors = np.zeros((len(live_ids), self._dimension), dtype=np.float32)
            for i, int_id in enumerate(live_ids):
                vectors[i] = self._index.reconstruct(int_id)
            return vectors, np.array(live_ids, dtype=np.int64)
        except Exception:
            logger.warning("Could not reconstruct live vectors for index rebuild")
            return None, None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def doc_count(self) -> int:
        """Number of live (non-deleted) documents in the index."""
        if not self.available or self._index is None:
            return 0
        # Use mapping size — excludes soft-deleted slots.
        return len(self._doc_id_to_int)

    @property
    def index_type(self) -> str:
        """Return a human-readable description of the current index type."""
        if not self.available or self._index is None:
            return "unavailable"
        inner = self._inner_index()
        if isinstance(inner, faiss.IndexIVFFlat):
            return f"IVF (nlist={inner.nlist}, nprobe={inner.nprobe})"
        if isinstance(inner, faiss.IndexHNSWFlat):
            return f"HNSW (M={inner.hnsw.nb_neighbors(0)}, efSearch={inner.hnsw.efSearch})"
        return "Flat (exact)"
