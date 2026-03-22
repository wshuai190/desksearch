"""Unit tests for the indexing pipeline."""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desksearch.config import Config
from desksearch.indexer.chunker import Chunk, chunk_text
from desksearch.indexer.parsers import (
    get_parser,
    parse_file,
    register_parser,
    _parse_text,
    _parse_code,
    _parse_ipynb,
)
from desksearch.indexer.store import MetadataStore
from desksearch.indexer.pipeline import IndexingPipeline, IndexStatus, StatusType


# --- Parser tests ---


class TestParsers:
    def test_text_parser(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("Hello, world!")
        assert parse_file(f) == "Hello, world!"

    def test_markdown_parser(self, tmp_path: Path):
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nSome content here.")
        assert parse_file(f) == "# Title\n\nSome content here."

    def test_code_parser(self, tmp_path: Path):
        f = tmp_path / "script.py"
        f.write_text("def hello():\n    print('hi')")
        result = parse_file(f)
        assert "[python]" in result
        assert "def hello():" in result

    def test_unknown_extension_returns_none(self, tmp_path: Path):
        f = tmp_path / "file.xyz123"
        f.write_text("some data")
        assert parse_file(f) is None

    def test_empty_file_returns_none(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        assert parse_file(f) is None

    def test_register_custom_parser(self, tmp_path: Path):
        def custom(path: Path) -> str:
            return "custom parsed"

        register_parser([".custom"], custom)
        assert get_parser(".custom") is custom

    def test_ipynb_parser(self, tmp_path: Path):
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Notebook"]},
                {"cell_type": "code", "source": ["x = 1"]},
            ]
        }
        f = tmp_path / "notebook.ipynb"
        f.write_text(json.dumps(notebook))
        result = parse_file(f)
        assert "# Notebook" in result
        assert "x = 1" in result

    def test_parse_handles_errors_gracefully(self, tmp_path: Path):
        """Parser errors should return None, not raise."""
        f = tmp_path / "bad.pdf"
        f.write_bytes(b"not a real pdf")
        result = parse_file(f)
        assert result is None


# --- Chunker tests ---


class TestChunker:
    def test_basic_chunking(self):
        text = "A" * 1000
        chunks = chunk_text(text, source_file="test.txt", chunk_size=512, chunk_overlap=64)
        assert len(chunks) >= 2
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_chunk_metadata(self):
        text = "Hello world. " * 100
        chunks = chunk_text(text, source_file="/path/to/file.txt")
        for i, chunk in enumerate(chunks):
            assert chunk.source_file == "/path/to/file.txt"
            assert chunk.chunk_index == i
            assert isinstance(chunk.char_offset, int)

    def test_small_text_single_chunk(self):
        text = "Short text."
        chunks = chunk_text(text, source_file="test.txt")
        assert len(chunks) == 1
        assert chunks[0].text == "Short text."

    def test_empty_text(self):
        assert chunk_text("", source_file="test.txt") == []
        assert chunk_text("   ", source_file="test.txt") == []

    def test_preserves_paragraphs(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = chunk_text(text, source_file="test.txt", chunk_size=1024)
        # Should be a single chunk since it fits
        assert len(chunks) == 1
        assert "Paragraph one." in chunks[0].text
        assert "Paragraph two." in chunks[0].text

    def test_overlap_present(self):
        # Create text that requires multiple chunks
        para = "Word " * 100  # ~500 chars
        text = f"{para}\n\n{para}\n\n{para}"
        chunks = chunk_text(text, source_file="test.txt", chunk_size=512, chunk_overlap=64)
        if len(chunks) >= 2:
            # The end of chunk N should overlap with start of chunk N+1
            end_of_first = chunks[0].text[-32:]
            assert end_of_first in chunks[1].text


# --- Store tests ---


class TestMetadataStore:
    def test_create_and_retrieve_document(self, tmp_path: Path):
        store = MetadataStore(tmp_path / "test.db")
        # Create a test file
        test_file = tmp_path / "doc.txt"
        test_file.write_text("hello")

        doc_id = store.upsert_document(test_file, num_chunks=3)
        assert doc_id > 0

        doc = store.get_document(test_file)
        assert doc is not None
        assert doc.filename == "doc.txt"
        assert doc.extension == ".txt"
        assert doc.num_chunks == 3
        store.close()

    def test_needs_indexing_new_file(self, tmp_path: Path):
        store = MetadataStore(tmp_path / "test.db")
        test_file = tmp_path / "new.txt"
        test_file.write_text("content")
        assert store.needs_indexing(test_file) is True
        store.close()

    def test_needs_indexing_unchanged_file(self, tmp_path: Path):
        store = MetadataStore(tmp_path / "test.db")
        test_file = tmp_path / "existing.txt"
        test_file.write_text("content")

        store.upsert_document(test_file, num_chunks=1)
        assert store.needs_indexing(test_file) is False
        store.close()

    def test_add_and_get_chunks(self, tmp_path: Path):
        store = MetadataStore(tmp_path / "test.db")
        test_file = tmp_path / "doc.txt"
        test_file.write_text("hello")

        doc_id = store.upsert_document(test_file, num_chunks=2)
        chunk_ids = store.add_chunks(doc_id, [
            ("chunk one", 0, 0),
            ("chunk two", 1, 100),
        ])
        assert len(chunk_ids) == 2

        chunks = store.get_chunks(doc_id)
        assert len(chunks) == 2
        assert chunks[0].text == "chunk one"
        assert chunks[1].chunk_index == 1
        store.close()

    def test_delete_document_cascades(self, tmp_path: Path):
        store = MetadataStore(tmp_path / "test.db")
        test_file = tmp_path / "doc.txt"
        test_file.write_text("hello")

        doc_id = store.upsert_document(test_file, num_chunks=1)
        store.add_chunks(doc_id, [("text", 0, 0)])

        assert store.delete_document(test_file) is True
        assert store.get_document(test_file) is None
        assert store.get_chunks(doc_id) == []
        store.close()

    def test_upsert_replaces_chunks(self, tmp_path: Path):
        store = MetadataStore(tmp_path / "test.db")
        test_file = tmp_path / "doc.txt"
        test_file.write_text("version 1")

        doc_id = store.upsert_document(test_file, num_chunks=1)
        store.add_chunks(doc_id, [("old chunk", 0, 0)])

        # Upsert again
        doc_id2 = store.upsert_document(test_file, num_chunks=2)
        assert doc_id2 == doc_id  # Same document
        store.add_chunks(doc_id, [("new chunk 1", 0, 0), ("new chunk 2", 1, 50)])

        chunks = store.get_chunks(doc_id)
        assert len(chunks) == 2
        assert chunks[0].text == "new chunk 1"
        store.close()

    def test_document_count(self, tmp_path: Path):
        store = MetadataStore(tmp_path / "test.db")
        assert store.document_count() == 0

        f1 = tmp_path / "a.txt"
        f1.write_text("a")
        f2 = tmp_path / "b.txt"
        f2.write_text("b")

        store.upsert_document(f1, num_chunks=1)
        store.upsert_document(f2, num_chunks=1)
        assert store.document_count() == 2
        store.close()


# --- Pipeline tests ---


class TestPipeline:
    def test_discover_files(self, tmp_path: Path):
        config = Config(
            data_dir=tmp_path / "data",
            index_paths=[tmp_path],
            file_extensions=[".txt", ".md", ".py"],
            excluded_dirs=["hidden"],
        )

        # Create test files
        (tmp_path / "readme.md").write_text("# Hello")
        (tmp_path / "notes.txt").write_text("notes")
        (tmp_path / "script.py").write_text("x = 1")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")

        # Create excluded directory
        (tmp_path / "hidden").mkdir()
        (tmp_path / "hidden" / "secret.txt").write_text("secret")

        pipeline = IndexingPipeline(config)
        files = pipeline.discover_files(tmp_path)

        filenames = [f.name for f in files]
        assert "readme.md" in filenames
        assert "notes.txt" in filenames
        assert "script.py" in filenames
        assert "image.png" not in filenames
        assert "secret.txt" not in filenames
        pipeline.close()

    def test_discover_respects_max_file_size(self, tmp_path: Path):
        config = Config(
            data_dir=tmp_path / "data",
            index_paths=[tmp_path],
            file_extensions=[".txt"],
            max_file_size_mb=1,  # 1 MB limit
        )

        small = tmp_path / "small.txt"
        small.write_text("small file")

        big = tmp_path / "big.txt"
        big.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB

        pipeline = IndexingPipeline(config)
        files = pipeline.discover_files(tmp_path)
        filenames = [f.name for f in files]
        assert "small.txt" in filenames
        assert "big.txt" not in filenames
        pipeline.close()

    @patch("desksearch.indexer.pipeline.Embedder")
    def test_index_file_yields_statuses(self, MockEmbedder, tmp_path: Path):
        import numpy as np

        mock_embedder = MockEmbedder.return_value
        mock_embedder.embed.return_value = np.random.rand(1, 384).astype(np.float32)

        config = Config(data_dir=tmp_path / "data")
        pipeline = IndexingPipeline(config)
        pipeline.embedder = mock_embedder

        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world, this is a test document.")

        statuses = []
        gen = pipeline.index_file(test_file)
        try:
            while True:
                statuses.append(next(gen))
        except StopIteration:
            pass

        status_types = [s.status for s in statuses]
        assert StatusType.PARSING in status_types
        assert StatusType.CHUNKING in status_types
        assert StatusType.EMBEDDING in status_types
        assert StatusType.STORING in status_types
        assert StatusType.COMPLETE in status_types
        pipeline.close()

    @patch("desksearch.indexer.pipeline.Embedder")
    def test_index_file_skips_up_to_date(self, MockEmbedder, tmp_path: Path):
        import numpy as np

        mock_embedder = MockEmbedder.return_value
        mock_embedder.embed.return_value = np.random.rand(1, 384).astype(np.float32)

        config = Config(data_dir=tmp_path / "data")
        pipeline = IndexingPipeline(config)
        pipeline.embedder = mock_embedder

        test_file = tmp_path / "test.txt"
        test_file.write_text("Content")

        # Index once
        for _ in pipeline.index_file(test_file):
            pass

        # Index again - should skip
        statuses = list(pipeline.index_file(test_file))
        assert any(s.status == StatusType.SKIPPED for s in statuses)
        pipeline.close()

    def test_remove_file(self, tmp_path: Path):
        config = Config(data_dir=tmp_path / "data")
        pipeline = IndexingPipeline(config)

        test_file = tmp_path / "test.txt"
        test_file.write_text("Content")

        pipeline.store.upsert_document(test_file, num_chunks=1)
        assert pipeline.remove_file(test_file) is True
        assert pipeline.store.get_document(test_file) is None
        pipeline.close()
