"""Main indexing pipeline.

Orchestrates file discovery, parsing, chunking, embedding, and storage.
Yields status updates for progress reporting.

Batch embedding: instead of embedding per-file, chunks are accumulated
across files and embedded in batches of up to 64 for 3-5x throughput.
"""
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Generator, Optional

import numpy as np

from desksearch.config import Config
from desksearch.indexer.chunker import chunk_text
from desksearch.indexer.embedder import Embedder
from desksearch.indexer.parsers import parse_file
from desksearch.indexer.store import MetadataStore

logger = logging.getLogger(__name__)

# Max chunks to accumulate before flushing an embedding batch.
BATCH_EMBED_SIZE = 64


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
        self.embedder = embedder or Embedder(self.config.embedding_model)
        self.search_engine = search_engine
        self._embeddings_path = self.config.data_dir / "embeddings"
        self._embeddings_path.mkdir(parents=True, exist_ok=True)

    def discover_files(self, directory: Path) -> list[Path]:
        """Discover all indexable files in a directory.

        Respects excluded_dirs and file_extensions from config.
        Skips files larger than max_file_size_mb.
        """
        extensions = set(self.config.file_extensions)
        excluded = set(self.config.excluded_dirs)
        max_size = self.config.max_file_size_mb * 1024 * 1024
        files: list[Path] = []

        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            # Check excluded directories
            if any(part in excluded for part in path.parts):
                continue
            # Check extension
            if path.suffix.lower() not in extensions:
                continue
            # Check file size
            try:
                if path.stat().st_size > max_size:
                    continue
            except OSError:
                continue
            files.append(path)

        return sorted(files)

    def index_file(self, path: Path) -> Generator[IndexStatus, None, Optional[np.ndarray]]:
        """Index a single file through the full pipeline.

        Yields status updates and returns the embeddings array (or None on failure).
        """
        file_t0 = time.perf_counter()
        path = path.resolve()

        # Check if re-indexing is needed
        if not self.store.needs_indexing(path):
            yield IndexStatus(StatusType.SKIPPED, str(path), "Already up to date")
            return None

        # Parse
        yield IndexStatus(StatusType.PARSING, str(path))
        t0 = time.perf_counter()
        text = parse_file(path)
        parse_ms = (time.perf_counter() - t0) * 1000
        if text is None:
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
            yield IndexStatus(StatusType.ERROR, str(path), "No chunks produced")
            return None
        logger.info("[%s] chunk: %.0fms (%d chunks)", path.name, chunk_ms, len(chunks))

        # Embed
        yield IndexStatus(StatusType.EMBEDDING, str(path), f"{len(chunks)} chunks")
        t0 = time.perf_counter()
        chunk_texts = [c.text for c in chunks]
        embeddings = self.embedder.embed(chunk_texts)
        embed_ms = (time.perf_counter() - t0) * 1000
        logger.info("[%s] embed: %.0fms (%d chunks)", path.name, embed_ms, len(chunks))

        # Store metadata
        yield IndexStatus(StatusType.STORING, str(path))
        t0 = time.perf_counter()
        doc_id = self.store.upsert_document(path, num_chunks=len(chunks))
        chunk_ids = self.store.add_chunks(
            doc_id,
            [(c.text, c.chunk_index, c.char_offset) for c in chunks],
        )
        store_ms = (time.perf_counter() - t0) * 1000
        logger.info("[%s] store: %.0fms", path.name, store_ms)

        # Feed into search engine if available
        t0 = time.perf_counter()
        if self.search_engine is not None:
            docs = [
                (str(cid), ct, emb)
                for cid, ct, emb in zip(chunk_ids, chunk_texts, embeddings)
            ]
            self.search_engine.add_documents(docs)
        index_ms = (time.perf_counter() - t0) * 1000
        logger.info("[%s] index: %.0fms", path.name, index_ms)

        total_ms = (time.perf_counter() - file_t0) * 1000
        logger.info(
            "[%s] total: %.0fms (parse=%.0f chunk=%.0f embed=%.0f store=%.0f index=%.0f)",
            path.name, total_ms, parse_ms, chunk_ms, embed_ms, store_ms, index_ms,
        )
        yield IndexStatus(StatusType.COMPLETE, str(path), f"{len(chunks)} chunks indexed")
        return embeddings

    def index_directory(
        self,
        directory: Path,
        batch_size: int = 32,
    ) -> Generator[IndexStatus, None, dict]:
        """Index all files in a directory.

        Collects chunks across files and embeds them in batches of up to
        BATCH_EMBED_SIZE for 3-5x throughput improvement.
        Yields status updates throughout.

        Returns a summary dict with counts.
        """
        directory = directory.resolve()

        # Discover
        yield IndexStatus(StatusType.DISCOVERY, str(directory), "Scanning...")
        files = self.discover_files(directory)
        yield IndexStatus(StatusType.DISCOVERY, str(directory), f"Found {len(files)} files")

        # Filter to files needing indexing
        files_to_index = [f for f in files if self.store.needs_indexing(f)]
        yield IndexStatus(
            StatusType.DISCOVERY,
            str(directory),
            f"{len(files_to_index)} files need indexing ({len(files) - len(files_to_index)} up to date)",
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
            nonlocal indexed, all_embeddings, all_chunk_ids

            if not pending_chunk_texts:
                return []

            t0 = time.perf_counter()
            embeddings = self.embedder.embed(pending_chunk_texts, batch_size=BATCH_EMBED_SIZE)
            embed_ms = (time.perf_counter() - t0) * 1000
            logger.info("batch embed: %.0fms (%d chunks)", embed_ms, len(pending_chunk_texts))

            # Store results per-file
            completed: list[tuple[Path, int]] = []
            emb_offset = 0
            for pf in pending_files:
                num_chunks = len(pf.chunks)
                file_embeddings = embeddings[emb_offset:emb_offset + num_chunks]
                emb_offset += num_chunks

                t0 = time.perf_counter()
                doc_id = self.store.upsert_document(pf.path, num_chunks=num_chunks)
                chunk_ids = self.store.add_chunks(
                    doc_id,
                    [(c.text, c.chunk_index, c.char_offset) for c in pf.chunks],
                )

                # Feed into search engine if available
                if self.search_engine is not None:
                    docs = [
                        (str(cid), ct, emb)
                        for cid, ct, emb in zip(chunk_ids, pf.chunk_texts, file_embeddings)
                    ]
                    self.search_engine.add_documents(docs)

                store_idx_ms = (time.perf_counter() - t0) * 1000
                logger.info("[%s] store+index: %.0fms", pf.path.name, store_idx_ms)

                all_embeddings.append(file_embeddings)
                all_chunk_ids.extend(chunk_ids)
                indexed += 1
                completed.append((pf.path, num_chunks))

            pending_files.clear()
            pending_chunk_texts.clear()
            return completed

        # Process files, accumulating chunks for batch embedding
        for i, file_path in enumerate(files_to_index):
            file_num = i + 1

            # Parse
            yield IndexStatus(StatusType.PARSING, str(file_path), current=file_num, total=len(files_to_index))
            t0 = time.perf_counter()
            try:
                text = parse_file(file_path)
            except Exception as e:
                yield IndexStatus(StatusType.ERROR, str(file_path), str(e))
                errors += 1
                continue

            if text is None:
                errors += 1
                continue
            parse_ms = (time.perf_counter() - t0) * 1000
            logger.info("[%s] parse: %.0fms", file_path.name, parse_ms)

            # Chunk
            t0 = time.perf_counter()
            chunks = chunk_text(
                text,
                source_file=str(file_path),
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
            )
            chunk_ms = (time.perf_counter() - t0) * 1000
            if not chunks:
                errors += 1
                continue
            logger.info("[%s] chunk: %.0fms (%d chunks)", file_path.name, chunk_ms, len(chunks))

            chunk_texts = [c.text for c in chunks]
            pending_files.append(_PendingFile(path=file_path, chunks=chunks, chunk_texts=chunk_texts))
            pending_chunk_texts.extend(chunk_texts)

            # Flush when batch is full
            if len(pending_chunk_texts) >= BATCH_EMBED_SIZE:
                yield IndexStatus(
                    StatusType.EMBEDDING,
                    message=f"Embedding {len(pending_chunk_texts)} chunks from {len(pending_files)} files",
                )
                completed = _flush_batch()
                for cpath, nchunks in completed:
                    yield IndexStatus(
                        StatusType.COMPLETE,
                        str(cpath),
                        f"{nchunks} chunks",
                        current=indexed,
                        total=len(files_to_index),
                    )

        # Flush remaining
        if pending_chunk_texts:
            yield IndexStatus(
                StatusType.EMBEDDING,
                message=f"Embedding {len(pending_chunk_texts)} chunks from {len(pending_files)} files",
            )
            completed = _flush_batch()
            for cpath, nchunks in completed:
                yield IndexStatus(
                    StatusType.COMPLETE,
                    str(cpath),
                    f"{nchunks} chunks",
                    current=indexed,
                    total=len(files_to_index),
                )

        # Save combined embeddings to disk
        if all_embeddings:
            combined = np.vstack(all_embeddings)
            np.save(
                str(self._embeddings_path / "embeddings.npy"),
                combined,
            )
            np.save(
                str(self._embeddings_path / "chunk_ids.npy"),
                np.array(all_chunk_ids, dtype=np.int64),
            )

        summary = {
            "indexed": indexed,
            "skipped": len(files) - len(files_to_index),
            "errors": errors,
            "total_files": len(files),
        }
        yield IndexStatus(
            StatusType.COMPLETE,
            str(directory),
            f"Done: {indexed} indexed, {skipped} skipped, {errors} errors",
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

    def remove_file(self, path: Path) -> bool:
        """Remove a file from the index."""
        return self.store.delete_document(path.resolve())

    def close(self) -> None:
        """Clean up resources."""
        self.store.close()
