"""Main indexing pipeline.

Orchestrates file discovery, parsing, chunking, embedding, and storage.
Yields status updates for progress reporting.

Batch embedding: instead of embedding per-file, chunks are accumulated
across files and embedded in batches of up to BATCH_EMBED_SIZE for 3-5x
throughput.

Parallel parsing: files are parsed + chunked in a thread pool while the
main thread embeds the previous batch. ONNX Runtime releases the GIL
during session.run(), so parse threads execute concurrently with embedding.
"""
import logging
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Generator, Optional

import numpy as np

from desksearch.config import Config
from desksearch.indexer.chunker import chunk_text
from desksearch.indexer.embedder import Embedder
from desksearch.indexer.parsers import parse_file
from desksearch.indexer.store import MetadataStore, compute_file_hash
from desksearch.utils.memory import log_memory, log_memory_delta

logger = logging.getLogger(__name__)

# Max chunks to accumulate before flushing an embedding batch.
# Larger = fewer flush calls, better ONNX throughput.
BATCH_EMBED_SIZE = 256

# Number of parallel file-parse workers.
# Parsing is I/O + CPU bound; 4 threads saturates disk while leaving cores
# for ONNX.  Keep it ≤ physical cores / 2 to avoid competing with ONNX GEMM.
PARSE_WORKERS = 6

# How many parse futures to keep in flight ahead of the embed cursor.
# Larger = better parse/embed overlap, more peak RAM for pending text.
PARSE_LOOKAHEAD = 16

# Per-file timeout for parse + chunk (seconds).
PARSE_TIMEOUT_SEC = 30

# Inner ONNX batch size: how many sequences per session.run() call.
# For Starbucks ONNX INT8 (middle tier): 32 is optimal on Apple M-series.
# For fast tier: 128 is optimal. The embedder auto-selects via _onnx_optimal_batch.
# This is the upper cap; the embedder may use a smaller batch internally.
ONNX_INNER_BATCH = 64


class StatusType(Enum):
    """Types of status updates from the pipeline."""
    DISCOVERY = "discovery"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    STORING = "storing"
    SKIPPED = "skipped"
    ERROR = "error"
    COMPLETE = "complete"


@dataclass
class IndexStatus:
    """A status update from the indexing pipeline."""
    status: StatusType
    file: Optional[str] = None
    message: str = ""
    current: int = 0
    total: int = 0


@dataclass
class _PendingFile:
    """Accumulator for a parsed + chunked file awaiting embedding."""
    path: Path
    chunks: list  # list of Chunk dataclass instances
    chunk_texts: list[str] = field(default_factory=list)
    content_hash: str = ""
    parse_ms: float = 0.0
    chunk_ms: float = 0.0


def _parse_and_chunk_file(
    file_path: Path,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[Optional[_PendingFile], Optional[str]]:
    """Parse and chunk a single file in a thread-pool worker.

    Returns (_PendingFile, None) on success or (None, error_message) on failure.
    Thread-safe: uses only read-only shared state (_PARSERS registry).
    """
    t0 = time.perf_counter()
    try:
        text = parse_file(file_path)
    except Exception as exc:  # noqa: BLE001
        return None, f"parse exception: {exc}"

    if text is None:
        return None, "parse_failed"
    parse_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    try:
        chunks = chunk_text(
            text,
            source_file=str(file_path),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"chunk exception: {exc}"

    if not chunks:
        return None, "no_chunks"
    chunk_ms = (time.perf_counter() - t1) * 1000

    # Compute content hash for skip-on-reindex optimisation
    try:
        content_hash = compute_file_hash(file_path)
    except OSError:
        content_hash = ""

    chunk_texts = [c.text for c in chunks]
    return _PendingFile(
        path=file_path, chunks=chunks, chunk_texts=chunk_texts,
        content_hash=content_hash, parse_ms=parse_ms, chunk_ms=chunk_ms,
    ), None


class IndexingPipeline:
    """Orchestrates the full indexing pipeline.

    Discovers files, parses them, chunks the text, generates embeddings,
    and stores everything in the BM25 index, dense index, and SQLite store.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        search_engine=None,
        embedder: Optional[Embedder] = None,
        store: Optional[MetadataStore] = None,
    ) -> None:
        self.config = config or Config()
        self.store = store or MetadataStore(self.config.data_dir / "metadata.db")
        self.config.resolve_starbucks_tier()
        self.embedder = embedder or Embedder(
            self.config.embedding_model,
            embedding_dim=self.config.embedding_dim,
            embedding_layers=self.config.embedding_layers,
        )
        self.search_engine = search_engine
        self._embeddings_path = self.config.data_dir / "embeddings"
        self._embeddings_path.mkdir(parents=True, exist_ok=True)

    def discover_files(self, directory: Path) -> list[Path]:
        """Discover all indexable files in a directory.

        Uses os.walk with directory pruning so that excluded dirs (e.g.
        .git, node_modules, __pycache__) are never descended into.  This
        is dramatically faster than rglob on large trees.
        """
        import os

        extensions = set(self.config.file_extensions)
        excluded = set(self.config.excluded_dirs)
        max_size = self.config.max_file_size_mb * 1024 * 1024
        files: list[Path] = []

        for dirpath, dirnames, filenames in os.walk(directory):
            # Prune excluded directories IN-PLACE so os.walk skips them
            dirnames[:] = [d for d in dirnames if d not in excluded]

            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in extensions:
                    continue
                full = os.path.join(dirpath, fname)
                try:
                    if os.path.getsize(full) > max_size:
                        continue
                except OSError:
                    continue
                files.append(Path(full))

        return sorted(files)

    def index_file(self, path: Path) -> Generator[IndexStatus, None, Optional[np.ndarray]]:
        """Index a single file through the full pipeline.

        Crash recovery: marks the file as 'indexing' in the store before
        processing begins.  If the process exits before finishing, the next
        run detects the 'indexing' state and re-tries the file.

        Yields status updates and returns the embeddings array (or None on failure).
        """
        file_t0 = time.perf_counter()
        path = path.resolve()

        # Check if re-indexing is needed
        if not self.store.needs_indexing(path):
            yield IndexStatus(StatusType.SKIPPED, str(path), "Already up to date")
            return None

        # Mark as in-progress BEFORE we do any work so that a crash mid-way
        # is detectable on the next run via needs_indexing().
        try:
            self.store.mark_indexing_started(path)
        except Exception as exc:
            logger.warning("[%s] Could not mark indexing started: %s", path.name, exc)

        # Parse
        yield IndexStatus(StatusType.PARSING, str(path))
        t0 = time.perf_counter()
        text = parse_file(path)
        parse_ms = (time.perf_counter() - t0) * 1000
        if text is None:
            self._mark_failed(path)
            yield IndexStatus(StatusType.ERROR, str(path), "Failed to parse")
            return None
        logger.info("[%s] parse: %.0fms (%d chars)", path.name, parse_ms, len(text))

        # Chunk
        yield IndexStatus(StatusType.CHUNKING, str(path))
        t0 = time.perf_counter()
        chunks = chunk_text(
            text,
            source_file=str(path),
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )
        chunk_ms = (time.perf_counter() - t0) * 1000
        if not chunks:
            self._mark_failed(path)
            yield IndexStatus(StatusType.ERROR, str(path), "No chunks produced")
            return None
        logger.info("[%s] chunk: %.0fms (%d chunks)", path.name, chunk_ms, len(chunks))

        # Embed
        yield IndexStatus(StatusType.EMBEDDING, str(path), f"{len(chunks)} chunks")
        t0 = time.perf_counter()
        chunk_texts = [c.text for c in chunks]
        try:
            embeddings = self.embedder.embed(chunk_texts)
        except Exception as exc:
            self._mark_failed(path)
            yield IndexStatus(StatusType.ERROR, str(path), f"Embedding failed: {exc}")
            return None
        embed_ms = (time.perf_counter() - t0) * 1000
        logger.info("[%s] embed: %.0fms (%d chunks)", path.name, embed_ms, len(chunks))

        # Compute content hash for reindex skip optimisation
        try:
            content_hash = compute_file_hash(path)
        except OSError:
            content_hash = ""

        # Store metadata
        yield IndexStatus(StatusType.STORING, str(path))
        t0 = time.perf_counter()
        try:
            doc_id = self.store.upsert_document(
                path, num_chunks=len(chunks), content_hash=content_hash,
            )
            chunk_ids = self.store.add_chunks(
                doc_id,
                [(c.text, c.chunk_index, c.char_offset) for c in chunks],
            )
        except Exception as exc:
            self._mark_failed(path)
            yield IndexStatus(StatusType.ERROR, str(path), f"Store failed: {exc}")
            return None
        store_ms = (time.perf_counter() - t0) * 1000
        logger.info("[%s] store: %.0fms", path.name, store_ms)

        # Feed into search engine if available
        t0 = time.perf_counter()
        if self.search_engine is not None:
            try:
                docs = [
                    (str(cid), ct, emb)
                    for cid, ct, emb in zip(chunk_ids, chunk_texts, embeddings)
                ]
                self.search_engine.add_documents(docs)
            except Exception as exc:
                logger.warning("[%s] Search engine update failed: %s", path.name, exc)
        index_ms = (time.perf_counter() - t0) * 1000
        logger.info("[%s] index: %.0fms", path.name, index_ms)

        total_ms = (time.perf_counter() - file_t0) * 1000
        logger.info(
            "[%s] total: %.0fms (parse=%.0f chunk=%.0f embed=%.0f store=%.0f index=%.0f)",
            path.name, total_ms, parse_ms, chunk_ms, embed_ms, store_ms, index_ms,
        )
        yield IndexStatus(StatusType.COMPLETE, str(path), f"{len(chunks)} chunks indexed")
        return embeddings

    def _mark_failed(self, path: Path) -> None:
        """Mark a file's indexing state as failed (best-effort)."""
        try:
            self.store.mark_indexing_failed(path)
        except Exception as exc:
            logger.warning("Could not mark indexing failed for %s: %s", path.name, exc)

    def index_directory(
        self,
        directory: Path,
        batch_size: int = 32,
    ) -> Generator[IndexStatus, None, dict]:
        """Index all files in a directory.

        Collects chunks across files and embeds them in batches of up to
        BATCH_EMBED_SIZE for throughput improvement.
        Yields status updates throughout.

        Returns a summary dict with counts.
        """
        directory = directory.resolve()
        mem_start = log_memory("index-directory-start")
        pipeline_t0 = time.perf_counter()

        # Per-stage accumulators (seconds)
        stage_times = {
            "discovery": 0.0,
            "parse": 0.0,
            "chunk": 0.0,
            "embed": 0.0,
            "store": 0.0,
            "index": 0.0,
        }
        total_chunks_produced = 0

        # Discover
        t_disc = time.perf_counter()
        yield IndexStatus(StatusType.DISCOVERY, str(directory), "Scanning...")
        files = self.discover_files(directory)
        yield IndexStatus(StatusType.DISCOVERY, str(directory), f"Found {len(files)} files")

        # Filter to files needing indexing
        files_to_index = [f for f in files if self.store.needs_indexing(f)]
        stage_times["discovery"] = time.perf_counter() - t_disc
        yield IndexStatus(
            StatusType.DISCOVERY,
            str(directory),
            f"{len(files_to_index)} files need indexing ({len(files) - len(files_to_index)} up to date)",
        )
        logger.info(
            "Discovery: %.0fms, %d files found, %d need indexing",
            stage_times["discovery"] * 1000, len(files), len(files_to_index),
        )

        indexed = 0
        skipped = 0
        errors = 0
        all_embeddings: list[np.ndarray] = []
        all_chunk_ids: list[int] = []

        # Accumulator for cross-file batch embedding
        pending_files: list[_PendingFile] = []
        pending_chunk_texts: list[str] = []

        def _flush_batch() -> list[tuple[Path, int]]:
            """Embed and store all accumulated chunks across files.

            Returns list of (path, num_chunks) for files that were stored,
            so the caller can yield COMPLETE statuses.
            """
            nonlocal indexed, all_embeddings, all_chunk_ids, total_chunks_produced

            if not pending_chunk_texts:
                return []

            n_chunks = len(pending_chunk_texts)
            n_files = len(pending_files)

            # Aggregate parse/chunk times from pending files
            for pf in pending_files:
                stage_times["parse"] += pf.parse_ms / 1000
                stage_times["chunk"] += pf.chunk_ms / 1000

            t0 = time.perf_counter()
            # Use ONNX_INNER_BATCH for the actual session.run() call size so
            # we control peak memory while still amortising call overhead over
            # a large accumulated batch.
            try:
                embeddings = self.embedder.embed(pending_chunk_texts, batch_size=ONNX_INNER_BATCH)
            except Exception as exc:
                logger.error("Batch embedding failed: %s", exc, exc_info=True)
                # Mark all pending files as failed
                for pf in pending_files:
                    self._mark_failed(pf.path)
                pending_files.clear()
                pending_chunk_texts.clear()
                return []

            embed_s = time.perf_counter() - t0
            stage_times["embed"] += embed_s
            logger.info(
                "batch embed: %.0fms (%d chunks from %d files, %.0f chunks/sec)",
                embed_s * 1000, n_chunks, n_files,
                n_chunks / embed_s if embed_s > 0 else 0,
            )

            # Store results per-file, then batch-add to search engine
            completed: list[tuple[Path, int]] = []
            batch_search_docs: list[tuple[str, str, np.ndarray]] = []
            emb_offset = 0
            for pf in pending_files:
                num_chunks = len(pf.chunks)
                file_embeddings = embeddings[emb_offset:emb_offset + num_chunks]
                emb_offset += num_chunks

                t_store = time.perf_counter()
                try:
                    doc_id = self.store.upsert_document(
                        pf.path, num_chunks=num_chunks,
                        content_hash=pf.content_hash,
                    )
                    chunk_ids = self.store.add_chunks(
                        doc_id,
                        [(c.text, c.chunk_index, c.char_offset) for c in pf.chunks],
                    )
                except Exception as exc:
                    logger.error("[%s] Store failed: %s", pf.path.name, exc, exc_info=True)
                    self._mark_failed(pf.path)
                    continue
                store_s = time.perf_counter() - t_store
                stage_times["store"] += store_s

                # Collect search engine docs for batch insert (defer_save)
                if self.search_engine is not None:
                    for cid, ct, emb in zip(chunk_ids, pf.chunk_texts, file_embeddings):
                        batch_search_docs.append((str(cid), ct, emb))

                all_embeddings.append(file_embeddings)
                all_chunk_ids.extend(chunk_ids)
                indexed += 1
                total_chunks_produced += num_chunks
                completed.append((pf.path, num_chunks))

            # Batch-add all docs to search engine with deferred save
            # (avoids writing FAISS index to disk after every file)
            if batch_search_docs and self.search_engine is not None:
                t_idx = time.perf_counter()
                try:
                    self.search_engine.add_documents(
                        batch_search_docs, defer_save=True,
                    )
                except Exception as exc:
                    logger.warning("Batch search engine update failed: %s", exc)
                stage_times["index"] += time.perf_counter() - t_idx

            pending_files.clear()
            pending_chunk_texts.clear()
            return completed

        # ------------------------------------------------------------------
        # Parallel parse + chunk loop with sliding lookahead window.
        #
        # PARSE_WORKERS threads parse+chunk files concurrently.  Because ONNX
        # Runtime releases the GIL during session.run(), parse threads run
        # *truly in parallel* with embedding, giving us free pipeline overlap.
        #
        # Ordering guarantee: futures are kept in a deque and consumed in
        # submission order, so progress statuses remain sequential.
        # ------------------------------------------------------------------
        import concurrent.futures as _cf

        file_iter = iter(files_to_index)
        n_total = len(files_to_index)

        with ThreadPoolExecutor(max_workers=PARSE_WORKERS) as executor:
            # Sliding window: deque of (file_path, Future)
            pending_futures: deque[tuple[Path, Future]] = deque()

            def _submit_next() -> None:
                """Submit the next file from file_iter to the parse pool."""
                try:
                    fp = next(file_iter)
                    fut = executor.submit(
                        _parse_and_chunk_file,
                        fp,
                        self.config.chunk_size,
                        self.config.chunk_overlap,
                    )
                    pending_futures.append((fp, fut))
                except StopIteration:
                    pass

            # Pre-fill the lookahead window
            for _ in range(min(PARSE_LOOKAHEAD, n_total)):
                _submit_next()

            file_num = 0
            while pending_futures:
                file_path, fut = pending_futures.popleft()
                file_num += 1

                # Keep the window full: submit next file while we wait
                _submit_next()

                # Mark as in-progress for crash recovery BEFORE blocking on
                # the future result.  If the process exits now, the next run
                # will re-index this file (needs_indexing returns True).
                try:
                    self.store.mark_indexing_started(file_path)
                except Exception as exc:
                    logger.debug("mark_indexing_started failed for %s: %s", file_path.name, exc)

                # Yield PARSING status immediately (non-blocking — the future
                # is likely already running or complete in a background thread)
                yield IndexStatus(
                    StatusType.PARSING, str(file_path),
                    current=file_num, total=n_total,
                )

                # Block until this file's parse+chunk is done (or times out)
                try:
                    pending_file, error = fut.result(timeout=PARSE_TIMEOUT_SEC)
                except _cf.TimeoutError:
                    yield IndexStatus(
                        StatusType.SKIPPED, str(file_path),
                        f"Skipped: parse+chunk took >{PARSE_TIMEOUT_SEC}s",
                    )
                    errors += 1
                    continue
                except Exception as exc:  # noqa: BLE001
                    yield IndexStatus(StatusType.ERROR, str(file_path), str(exc))
                    errors += 1
                    continue

                if error or pending_file is None:
                    if error not in ("parse_failed", "no_chunks"):
                        yield IndexStatus(StatusType.ERROR, str(file_path), error or "unknown error")
                    self._mark_failed(file_path)
                    errors += 1
                    continue

                # Accumulate into cross-file batch
                pending_files.append(pending_file)
                pending_chunk_texts.extend(pending_file.chunk_texts)

                # Flush when batch is full.
                # While _flush_batch() runs embed (ONNX releases GIL),
                # background threads parse the next PARSE_LOOKAHEAD files.
                if len(pending_chunk_texts) >= BATCH_EMBED_SIZE:
                    yield IndexStatus(
                        StatusType.EMBEDDING,
                        message=f"Embedding {len(pending_chunk_texts)} chunks from {len(pending_files)} files",
                        current=file_num,
                        total=n_total,
                    )
                    completed = _flush_batch()
                    for cpath, nchunks in completed:
                        yield IndexStatus(
                            StatusType.COMPLETE,
                            str(cpath),
                            f"{nchunks} chunks",
                            current=indexed,
                            total=n_total,
                        )

        # Flush remaining chunks after all files are parsed
        if pending_chunk_texts:
            yield IndexStatus(
                StatusType.EMBEDDING,
                message=f"Embedding {len(pending_chunk_texts)} chunks from {len(pending_files)} files",
                current=n_total,
                total=n_total,
            )
            completed = _flush_batch()
            for cpath, nchunks in completed:
                yield IndexStatus(
                    StatusType.COMPLETE,
                    str(cpath),
                    f"{nchunks} chunks",
                    current=indexed,
                    total=n_total,
                )

        # Save combined embeddings to disk as float16 (half the size/RAM of float32).
        # FAISS and the warm-up loader convert back to float32 on load.
        if all_embeddings:
            mem_pre = log_memory("before-embeddings-save")
            combined = np.vstack(all_embeddings).astype(np.float16)
            np.save(
                str(self._embeddings_path / "embeddings.npy"),
                combined,
            )
            np.save(
                str(self._embeddings_path / "chunk_ids.npy"),
                np.array(all_chunk_ids, dtype=np.int64),
            )
            del combined  # release before returning
            log_memory_delta(mem_pre, "after-embeddings-save")

        # Persist search engine indexes (FAISS + BM25) now that all batches
        # used defer_save=True.  One disk write instead of per-batch.
        if self.search_engine is not None:
            try:
                self.search_engine.save()
            except Exception as exc:
                logger.warning("Failed to save search engine index: %s", exc)

        log_memory_delta(mem_start, "index-directory-end")

        pipeline_elapsed = time.perf_counter() - pipeline_t0
        files_per_sec = indexed / pipeline_elapsed if pipeline_elapsed > 0 else 0
        chunks_per_sec = total_chunks_produced / pipeline_elapsed if pipeline_elapsed > 0 else 0

        logger.info(
            "Pipeline complete: %d files in %.1fs (%.1f files/sec, %.0f chunks/sec)",
            indexed, pipeline_elapsed, files_per_sec, chunks_per_sec,
        )
        for stage, secs in stage_times.items():
            logger.info("  stage %-10s: %.1fs", stage, secs)

        summary = {
            "indexed": indexed,
            "skipped": len(files) - len(files_to_index),
            "errors": errors,
            "total_files": len(files),
            "total_chunks": total_chunks_produced,
            "elapsed_sec": pipeline_elapsed,
            "files_per_sec": files_per_sec,
            "chunks_per_sec": chunks_per_sec,
            "stage_times": stage_times,
        }
        yield IndexStatus(
            StatusType.COMPLETE,
            str(directory),
            f"Done: {indexed} indexed, {skipped} skipped, {errors} errors "
            f"({files_per_sec:.1f} files/sec)",
        )
        return summary

    def reindex_all(self) -> Generator[IndexStatus, None, dict]:
        """Re-index all configured directories.

        Yields status updates. Returns combined summary.
        """
        total_summary = {"indexed": 0, "skipped": 0, "errors": 0, "total_files": 0}

        for directory in self.config.index_paths:
            if not directory.exists():
                yield IndexStatus(StatusType.ERROR, str(directory), "Directory does not exist")
                continue

            gen = self.index_directory(directory)
            try:
                while True:
                    status = next(gen)
                    yield status
            except StopIteration as e:
                if e.value:
                    for key in total_summary:
                        total_summary[key] += e.value.get(key, 0)

        return total_summary

    def index_single_file(self, path: Path) -> bool:
        """Index a single file synchronously (not a generator).

        Parses → chunks → embeds → stores → adds to search engine.
        Returns True on success, False on failure.
        Used by the file watcher for incremental indexing.
        """
        path = path.resolve()
        logger.info("[incremental] Indexing single file: %s", path)

        # Mark as in-progress for crash recovery
        try:
            self.store.mark_indexing_started(path)
        except Exception as exc:
            logger.warning("[%s] Could not mark indexing started: %s", path.name, exc)

        # Parse
        try:
            text = parse_file(path)
        except Exception as exc:
            logger.error("[%s] Parse failed: %s", path.name, exc)
            self._mark_failed(path)
            return False

        if text is None:
            logger.warning("[%s] Parse returned None", path.name)
            self._mark_failed(path)
            return False

        # Chunk
        try:
            chunks = chunk_text(
                text,
                source_file=str(path),
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
            )
        except Exception as exc:
            logger.error("[%s] Chunking failed: %s", path.name, exc)
            self._mark_failed(path)
            return False

        if not chunks:
            logger.warning("[%s] No chunks produced", path.name)
            self._mark_failed(path)
            return False

        # Embed
        chunk_texts = [c.text for c in chunks]
        try:
            embeddings = self.embedder.embed(chunk_texts)
        except Exception as exc:
            logger.error("[%s] Embedding failed: %s", path.name, exc)
            self._mark_failed(path)
            return False

        # Store
        try:
            doc_id = self.store.upsert_document(path, num_chunks=len(chunks))
            chunk_ids = self.store.add_chunks(
                doc_id,
                [(c.text, c.chunk_index, c.char_offset) for c in chunks],
            )
        except Exception as exc:
            logger.error("[%s] Store failed: %s", path.name, exc)
            self._mark_failed(path)
            return False

        # Add to search engine
        if self.search_engine is not None:
            try:
                docs = [
                    (str(cid), ct, emb)
                    for cid, ct, emb in zip(chunk_ids, chunk_texts, embeddings)
                ]
                self.search_engine.add_documents(docs)
            except Exception as exc:
                logger.warning("[%s] Search engine update failed: %s", path.name, exc)

        logger.info("[%s] Incremental index complete: %d chunks", path.name, len(chunks))
        return True

    def remove_file(self, path: Path) -> bool:
        """Remove a file from the index (store + search engine)."""
        path = path.resolve()
        # Remove chunks from search engine first
        if self.search_engine is not None:
            doc_record = self.store.get_document(path)
            if doc_record is not None:
                chunks = self.store.get_chunks(doc_record.id)
                for chunk in chunks:
                    try:
                        self.search_engine.delete_document(str(chunk.id))
                    except Exception as exc:
                        logger.warning("Failed to remove chunk %d from search engine: %s", chunk.id, exc)
        return self.store.delete_document(path)

    def close(self) -> None:
        """Clean up resources."""
        self.store.close()
