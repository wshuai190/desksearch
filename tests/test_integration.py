"""Integration tests for the full DeskSearch pipeline.

End-to-end tests that exercise indexing, search, and incremental updates
working together as a complete system.
"""
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from desksearch.config import Config
from desksearch.core.search import HybridSearchEngine, SearchResult
from desksearch.indexer.pipeline import IndexingPipeline, StatusType


DIM = 32


def _deterministic_embedder(keyword_vectors: dict[str, np.ndarray]):
    """Create a mock Embedder that returns deterministic vectors.

    For each text, if it contains a keyword from keyword_vectors, use that
    vector (with small noise). Otherwise return a random vector.
    """
    mock = MagicMock()
    mock.dimension = DIM

    def _embed(texts, batch_size=64):
        vecs = []
        for text in texts:
            matched = False
            for keyword, vec in keyword_vectors.items():
                if keyword.lower() in text.lower():
                    noise = np.random.randn(DIM).astype(np.float32) * 0.01
                    vecs.append(vec + noise)
                    matched = True
                    break
            if not matched:
                vecs.append(np.random.randn(DIM).astype(np.float32))
        return np.array(vecs, dtype=np.float32)

    mock.embed = _embed
    mock.embed_query = lambda q: _embed([q])[0]
    return mock


def _make_keyword_vectors(*keywords: str) -> dict[str, np.ndarray]:
    """Generate orthogonal-ish vectors for distinct keywords."""
    vecs = {}
    for i, kw in enumerate(keywords):
        v = np.zeros(DIM, dtype=np.float32)
        v[i % DIM] = 1.0
        vecs[kw] = v
    return vecs


# ---------------------------------------------------------------------------
# End-to-end: index files → search → verify results
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """Index real files on disk, search, and verify results come back."""

    def test_index_and_search(self, tmp_path: Path):
        kv = _make_keyword_vectors("python", "javascript", "cooking")
        embedder = _deterministic_embedder(kv)

        config = Config(data_dir=tmp_path / "data")
        engine = HybridSearchEngine(config, dimension=DIM)

        # Create test files
        (tmp_path / "python_guide.txt").write_text(
            "Python is a versatile programming language used for web development, "
            "data science, machine learning, and automation."
        )
        (tmp_path / "js_intro.txt").write_text(
            "JavaScript is the language of the web. It powers interactive websites "
            "and modern frontend frameworks like React and Vue."
        )
        (tmp_path / "recipe.txt").write_text(
            "Cooking a great pasta requires fresh ingredients, good olive oil, "
            "and patience. Season with salt and pepper."
        )

        # Index files through the pipeline
        pipeline_config = Config(
            data_dir=tmp_path / "data",
            index_paths=[tmp_path],
            file_extensions=[".txt"],
        )
        pipeline = IndexingPipeline(pipeline_config, search_engine=engine)
        pipeline.embedder = embedder

        statuses = list(pipeline.index_directory(tmp_path))
        complete_statuses = [s for s in statuses if s.status == StatusType.COMPLETE]
        assert len(complete_statuses) >= 3  # 3 files + final summary

        # Search for python — should find python_guide
        query_emb = embedder.embed_query("python programming")
        results = engine.search_sync("python programming", query_emb, top_k=5)
        assert len(results) >= 1

        # The top result should be from a python-related chunk
        top_texts = []
        for r in results[:2]:
            text = engine._doc_texts.get(r.doc_id, "")
            top_texts.append(text)
        assert any("Python" in t for t in top_texts)

        # Search for cooking
        query_emb = embedder.embed_query("cooking pasta recipe")
        results = engine.search_sync("cooking pasta recipe", query_emb, top_k=5)
        assert len(results) >= 1
        top_texts = [engine._doc_texts.get(r.doc_id, "") for r in results[:2]]
        assert any("pasta" in t.lower() for t in top_texts)

        pipeline.close()

    def test_search_returns_snippets(self, tmp_path: Path):
        kv = _make_keyword_vectors("quantum")
        embedder = _deterministic_embedder(kv)

        config = Config(data_dir=tmp_path / "data")
        engine = HybridSearchEngine(config, dimension=DIM)

        text = (
            "Quantum computing leverages quantum mechanical phenomena. "
            "Qubits can exist in superposition states. "
            "This enables quantum computers to solve certain problems exponentially faster."
        )
        emb = embedder.embed_query("quantum computing")
        engine.add_document("quantum_doc", text, emb)

        results = engine.search_sync("quantum computing", emb, top_k=5)
        assert len(results) >= 1
        assert results[0].snippets
        assert any("quantum" in s.text.lower() for s in results[0].snippets)


# ---------------------------------------------------------------------------
# Hybrid search vs BM25-only
# ---------------------------------------------------------------------------


class TestHybridVsBM25:
    """Verify that hybrid search can outperform BM25 alone."""

    def test_hybrid_finds_semantic_match(self, tmp_path: Path):
        """Dense retrieval should find semantically related docs that BM25 misses.

        We index a doc about 'machine learning algorithms' and query with
        'ML models' — BM25 won't match well (no shared tokens), but dense
        retrieval with aligned embeddings will.
        """
        # Both 'machine learning' and 'ML' map to the same vector
        base_vec = np.zeros(DIM, dtype=np.float32)
        base_vec[0] = 1.0
        kv = {"machine learning": base_vec, "ML": base_vec.copy()}
        embedder = _deterministic_embedder(kv)

        config = Config(data_dir=tmp_path / "data")
        engine = HybridSearchEngine(config, dimension=DIM)

        engine.add_document(
            "ml_doc",
            "Machine learning algorithms for classification and regression",
            embedder.embed_query("machine learning"),
        )
        engine.add_document(
            "unrelated_doc",
            "Gardening tips for growing tomatoes in spring",
            embedder.embed_query("gardening tomatoes"),
        )

        query_emb = embedder.embed_query("ML models")

        # BM25-only (alpha=0): "ML models" shares no tokens with "Machine learning..."
        bm25_results = engine.search_sync("ML models", query_emb, alpha=0.0, top_k=5)

        # Hybrid (alpha=0.5): dense component should boost ml_doc
        hybrid_results = engine.search_sync("ML models", query_emb, alpha=0.5, top_k=5)

        # Dense-only (alpha=1.0): should strongly prefer ml_doc
        dense_results = engine.search_sync("ML models", query_emb, alpha=1.0, top_k=5)

        # Dense should rank ml_doc first since embeddings are aligned
        assert len(dense_results) >= 1
        assert dense_results[0].doc_id == "ml_doc"

        # If BM25 returns results, hybrid should still have ml_doc ranked well
        if hybrid_results:
            hybrid_ids = [r.doc_id for r in hybrid_results]
            assert "ml_doc" in hybrid_ids

    def test_bm25_boosts_exact_match(self, tmp_path: Path):
        """BM25 component should boost exact keyword matches.

        When both docs have similar embeddings, BM25 breaks the tie
        in favor of the doc with the exact query terms.
        """
        shared_vec = np.ones(DIM, dtype=np.float32) / np.sqrt(DIM)
        kv = {"data": shared_vec}
        embedder = _deterministic_embedder(kv)

        config = Config(data_dir=tmp_path / "data")
        engine = HybridSearchEngine(config, dimension=DIM)

        engine.add_document(
            "exact_match",
            "Data science and data analysis are critical for business intelligence",
            embedder.embed_query("data science"),
        )
        engine.add_document(
            "partial_match",
            "Information processing and number crunching for analytics",
            embedder.embed_query("data analytics"),
        )

        query_emb = embedder.embed_query("data science analysis")

        # BM25-heavy search should prefer exact_match
        results = engine.search_sync("data science analysis", query_emb, alpha=0.0, top_k=5)
        if results:
            assert results[0].doc_id == "exact_match"


# ---------------------------------------------------------------------------
# Incremental indexing
# ---------------------------------------------------------------------------


class TestIncrementalIndexing:
    """Test that adding a new file and re-indexing picks it up."""

    @patch("desksearch.indexer.pipeline.Embedder")
    def test_incremental_index_finds_new_file(self, MockEmbedder, tmp_path: Path):
        mock_embedder = MockEmbedder.return_value
        mock_embedder.embed.return_value = np.random.rand(1, 64).astype(np.float32)

        config = Config(
            data_dir=tmp_path / "data",
            index_paths=[tmp_path / "docs"],
            file_extensions=[".txt"],
        )

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create initial file and index
        (docs_dir / "file1.txt").write_text("Original document about databases")

        pipeline = IndexingPipeline(config)
        pipeline.embedder = mock_embedder
        statuses = list(pipeline.index_directory(docs_dir))
        complete = [s for s in statuses if s.status == StatusType.COMPLETE]
        assert len(complete) >= 1

        # Verify file1 is indexed
        doc = pipeline.store.get_document((docs_dir / "file1.txt").resolve())
        assert doc is not None

        # Add a new file
        (docs_dir / "file2.txt").write_text("New document about networking")
        mock_embedder.embed.return_value = np.random.rand(1, 64).astype(np.float32)

        # Re-index — should pick up file2 and skip file1
        statuses2 = list(pipeline.index_directory(docs_dir))
        status_types = [s.status for s in statuses2]

        # file2 should be indexed
        doc2 = pipeline.store.get_document((docs_dir / "file2.txt").resolve())
        assert doc2 is not None

        # file1 should have been skipped (already up to date)
        assert pipeline.store.document_count() == 2
        pipeline.close()

    @patch("desksearch.indexer.pipeline.Embedder")
    def test_modified_file_gets_reindexed(self, MockEmbedder, tmp_path: Path):
        """When a file is modified, it should be re-indexed on the next run."""
        import time

        mock_embedder = MockEmbedder.return_value
        mock_embedder.embed.return_value = np.random.rand(1, 64).astype(np.float32)

        config = Config(
            data_dir=tmp_path / "data",
            index_paths=[tmp_path / "docs"],
            file_extensions=[".txt"],
        )

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        f = docs_dir / "mutable.txt"
        f.write_text("Version 1 content")

        pipeline = IndexingPipeline(config)
        pipeline.embedder = mock_embedder

        # First index
        list(pipeline.index_directory(docs_dir))
        doc1 = pipeline.store.get_document(f.resolve())
        assert doc1 is not None

        # Modify the file (ensure mtime changes)
        time.sleep(0.05)
        f.write_text("Version 2 content with extra information")

        # The store should detect the file needs re-indexing
        assert pipeline.store.needs_indexing(f.resolve()) is True

        # Re-index
        mock_embedder.embed.return_value = np.random.rand(1, 64).astype(np.float32)
        list(pipeline.index_directory(docs_dir))

        doc2 = pipeline.store.get_document(f.resolve())
        assert doc2 is not None
        pipeline.close()

    @patch("desksearch.indexer.pipeline.Embedder")
    def test_deleted_file_removed_from_index(self, MockEmbedder, tmp_path: Path):
        mock_embedder = MockEmbedder.return_value
        mock_embedder.embed.return_value = np.random.rand(1, 64).astype(np.float32)

        config = Config(
            data_dir=tmp_path / "data",
            file_extensions=[".txt"],
        )

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        f = docs_dir / "ephemeral.txt"
        f.write_text("Temporary content")

        pipeline = IndexingPipeline(config)
        pipeline.embedder = mock_embedder

        # Index the file
        list(pipeline.index_file(f))
        assert pipeline.store.get_document(f.resolve()) is not None

        # Remove via pipeline
        assert pipeline.remove_file(f) is True
        assert pipeline.store.get_document(f.resolve()) is None
        pipeline.close()


# ---------------------------------------------------------------------------
# Pipeline + search engine wiring
# ---------------------------------------------------------------------------


class TestPipelineSearchIntegration:
    """Verify that the pipeline correctly feeds chunks into the search engine."""

    def test_pipeline_feeds_search_engine(self, tmp_path: Path):
        kv = _make_keyword_vectors("astronomy", "biology")
        embedder = _deterministic_embedder(kv)

        config = Config(
            data_dir=tmp_path / "data",
            index_paths=[tmp_path / "docs"],
            file_extensions=[".txt"],
        )
        engine = HybridSearchEngine(config, dimension=DIM)
        pipeline = IndexingPipeline(config, search_engine=engine)
        pipeline.embedder = embedder

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "stars.txt").write_text(
            "Astronomy is the study of celestial objects and phenomena."
        )
        (docs_dir / "cells.txt").write_text(
            "Biology examines living organisms and their interactions."
        )

        list(pipeline.index_directory(docs_dir))

        # Engine should now have documents
        assert engine.doc_count >= 2

        # Search should find astronomy doc
        query_emb = embedder.embed_query("astronomy stars")
        results = engine.search_sync("astronomy stars", query_emb, top_k=5)
        assert len(results) >= 1

        # At least one result should mention astronomy
        found = False
        for r in results:
            text = engine._doc_texts.get(r.doc_id, "")
            if "astronomy" in text.lower() or "celestial" in text.lower():
                found = True
                break
        assert found, "Expected to find astronomy-related document in search results"

        pipeline.close()
