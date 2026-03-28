"""Unit tests for the core search engine."""

import asyncio
import tempfile
from pathlib import Path

import numpy as np
import pytest

from desksearch.config import Config
from desksearch.core.bm25 import BM25Index
from desksearch.core.dense import DenseIndex
from desksearch.core.fusion import FusedResult, reciprocal_rank_fusion, weighted_rrf
from desksearch.core.search import HybridSearchEngine, SearchResult
from desksearch.core.snippets import Snippet, extract_snippets


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def config(tmp_data_dir: Path) -> Config:
    return Config(data_dir=tmp_data_dir)


# ---------------------------------------------------------------------------
# BM25 tests
# ---------------------------------------------------------------------------


class TestBM25Index:
    def test_add_and_search(self, tmp_data_dir: Path) -> None:
        idx = BM25Index(tmp_data_dir)
        idx.add_document("doc1", "the quick brown fox jumps over the lazy dog")
        idx.add_document("doc2", "a fast red car drives on the highway")

        results = idx.search("quick fox")
        assert len(results) >= 1
        doc_ids = [r[0] for r in results]
        assert "doc1" in doc_ids

    def test_search_empty_query(self, tmp_data_dir: Path) -> None:
        idx = BM25Index(tmp_data_dir)
        idx.add_document("doc1", "hello world")
        assert idx.search("") == []
        assert idx.search("   ") == []

    def test_delete_document(self, tmp_data_dir: Path) -> None:
        idx = BM25Index(tmp_data_dir)
        idx.add_document("doc1", "python programming language")
        assert idx.doc_count == 1

        idx.delete_document("doc1")
        results = idx.search("python")
        assert all(r[0] != "doc1" for r in results)

    def test_batch_add(self, tmp_data_dir: Path) -> None:
        idx = BM25Index(tmp_data_dir)
        docs = [
            ("d1", "machine learning is great"),
            ("d2", "deep learning neural networks"),
            ("d3", "natural language processing"),
        ]
        idx.add_documents(docs)
        assert idx.doc_count == 3

        results = idx.search("learning")
        doc_ids = {r[0] for r in results}
        assert "d1" in doc_ids or "d2" in doc_ids

    def test_update_document(self, tmp_data_dir: Path) -> None:
        idx = BM25Index(tmp_data_dir)
        idx.add_document("doc1", "old content about cats")
        idx.add_document("doc1", "new content about dogs")

        results = idx.search("dogs")
        assert any(r[0] == "doc1" for r in results)

    def test_get_document(self, tmp_data_dir: Path) -> None:
        idx = BM25Index(tmp_data_dir)
        idx.add_document("doc1", "hello world test")
        body = idx.get_document("doc1")
        assert body is not None
        assert "hello" in body

    def test_doc_count(self, tmp_data_dir: Path) -> None:
        idx = BM25Index(tmp_data_dir)
        assert idx.doc_count == 0
        idx.add_document("a", "text")
        assert idx.doc_count == 1


# ---------------------------------------------------------------------------
# Dense index tests
# ---------------------------------------------------------------------------


class TestDenseIndex:
    DIM = 32  # Small dimension for tests

    def _random_emb(self) -> np.ndarray:
        return np.random.randn(self.DIM).astype(np.float32)

    def test_add_and_search(self, tmp_data_dir: Path) -> None:
        idx = DenseIndex(tmp_data_dir, dimension=self.DIM)
        emb = self._random_emb()
        idx.add("doc1", emb)

        results = idx.search(emb, top_k=5)
        assert len(results) >= 1
        assert results[0][0] == "doc1"
        assert results[0][1] > 0.99  # Should be very similar to itself

    def test_batch_add(self, tmp_data_dir: Path) -> None:
        idx = DenseIndex(tmp_data_dir, dimension=self.DIM)
        items = [(f"doc{i}", self._random_emb()) for i in range(5)]
        idx.add_batch(items)
        assert idx.doc_count == 5

    def test_delete(self, tmp_data_dir: Path) -> None:
        idx = DenseIndex(tmp_data_dir, dimension=self.DIM)
        idx.add("doc1", self._random_emb())
        assert idx.doc_count == 1
        idx.delete("doc1")
        assert idx.doc_count == 0

    def test_search_empty_index(self, tmp_data_dir: Path) -> None:
        idx = DenseIndex(tmp_data_dir, dimension=self.DIM)
        results = idx.search(self._random_emb(), top_k=5)
        assert results == []

    def test_persistence(self, tmp_data_dir: Path) -> None:
        emb = self._random_emb()
        idx1 = DenseIndex(tmp_data_dir, dimension=self.DIM)
        idx1.add("doc1", emb)
        del idx1

        idx2 = DenseIndex(tmp_data_dir, dimension=self.DIM)
        assert idx2.doc_count == 1
        results = idx2.search(emb, top_k=1)
        assert results[0][0] == "doc1"

    def test_update_replaces(self, tmp_data_dir: Path) -> None:
        idx = DenseIndex(tmp_data_dir, dimension=self.DIM)
        idx.add("doc1", self._random_emb())
        idx.add("doc1", self._random_emb())
        assert idx.doc_count == 1

    def test_cosine_similarity_ordering(self, tmp_data_dir: Path) -> None:
        idx = DenseIndex(tmp_data_dir, dimension=self.DIM)
        query = np.ones(self.DIM, dtype=np.float32)
        similar = query + np.random.randn(self.DIM).astype(np.float32) * 0.1
        different = -query + np.random.randn(self.DIM).astype(np.float32) * 0.1

        idx.add("similar", similar)
        idx.add("different", different)

        results = idx.search(query, top_k=2)
        assert results[0][0] == "similar"
        assert results[0][1] > results[1][1]


# ---------------------------------------------------------------------------
# Fusion tests
# ---------------------------------------------------------------------------


class TestFusion:
    def test_rrf_basic(self) -> None:
        bm25 = [("a", 10.0), ("b", 5.0), ("c", 1.0)]
        dense = [("b", 0.9), ("c", 0.8), ("a", 0.7)]

        fused = reciprocal_rank_fusion(bm25, dense, k=60)
        assert len(fused) == 3
        # All docs should be present
        ids = {r.doc_id for r in fused}
        assert ids == {"a", "b", "c"}
        # Scores should be positive
        assert all(r.score > 0 for r in fused)

    def test_rrf_preserves_ranks(self) -> None:
        bm25 = [("a", 10.0), ("b", 5.0)]
        dense = [("c", 0.9), ("a", 0.5)]

        fused = reciprocal_rank_fusion(bm25, dense, k=60)
        result_map = {r.doc_id: r for r in fused}
        assert result_map["a"].bm25_rank == 1
        assert result_map["a"].dense_rank == 2
        assert result_map["b"].bm25_rank == 2
        assert result_map["b"].dense_rank is None
        assert result_map["c"].dense_rank == 1

    def test_rrf_empty_input(self) -> None:
        assert reciprocal_rank_fusion() == []

    def test_rrf_single_system(self) -> None:
        results = [("a", 5.0), ("b", 3.0)]
        fused = reciprocal_rank_fusion(results, k=60)
        assert fused[0].doc_id == "a"
        assert fused[0].score > fused[1].score

    def test_weighted_rrf(self) -> None:
        bm25 = [("a", 10.0)]
        dense = [("b", 0.9)]

        # alpha=0 means BM25 only
        fused_bm25 = weighted_rrf(bm25, dense, alpha=0.0)
        assert fused_bm25[0].doc_id == "a"

        # alpha=1 means dense only
        fused_dense = weighted_rrf(bm25, dense, alpha=1.0)
        assert fused_dense[0].doc_id == "b"

    def test_rrf_weight_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            reciprocal_rank_fusion([("a", 1.0)], weights=[1.0, 2.0])

    def test_rrf_doc_in_both_scores_higher(self) -> None:
        bm25 = [("a", 10.0), ("b", 5.0)]
        dense = [("a", 0.9), ("c", 0.5)]

        fused = reciprocal_rank_fusion(bm25, dense, k=60)
        # "a" appears in both lists so should score highest
        assert fused[0].doc_id == "a"


# ---------------------------------------------------------------------------
# Snippet tests
# ---------------------------------------------------------------------------


class TestSnippets:
    SAMPLE_TEXT = (
        "Python is a high-level programming language. "
        "It supports multiple paradigms including object-oriented programming. "
        "Python is widely used for web development, data science, and machine learning. "
        "The language was created by Guido van Rossum and first released in 1991."
    )

    def test_basic_extraction(self) -> None:
        snippets = extract_snippets(self.SAMPLE_TEXT, "python programming")
        assert len(snippets) >= 1
        assert any("Python" in s.text for s in snippets)

    def test_highlighting(self) -> None:
        snippets = extract_snippets(self.SAMPLE_TEXT, "python")
        assert len(snippets) >= 1
        assert "<mark>" in snippets[0].highlighted
        assert "</mark>" in snippets[0].highlighted

    def test_custom_highlight_tags(self) -> None:
        snippets = extract_snippets(
            self.SAMPLE_TEXT, "python", highlight_tag=("**", "**")
        )
        assert len(snippets) >= 1
        assert "**Python**" in snippets[0].highlighted

    def test_empty_query(self) -> None:
        assert extract_snippets(self.SAMPLE_TEXT, "") == []
        assert extract_snippets(self.SAMPLE_TEXT, "   ") == []

    def test_empty_text(self) -> None:
        assert extract_snippets("", "python") == []

    def test_no_matches(self) -> None:
        assert extract_snippets(self.SAMPLE_TEXT, "xyznotfound") == []

    def test_max_snippets_limit(self) -> None:
        long_text = " ".join([self.SAMPLE_TEXT] * 10)
        snippets = extract_snippets(long_text, "python", max_snippets=2)
        assert len(snippets) <= 2

    def test_snippet_has_positions(self) -> None:
        snippets = extract_snippets(self.SAMPLE_TEXT, "Guido")
        assert len(snippets) >= 1
        s = snippets[0]
        assert s.start >= 0
        assert s.end > s.start
        assert s.end <= len(self.SAMPLE_TEXT)


# ---------------------------------------------------------------------------
# Hybrid search engine tests
# ---------------------------------------------------------------------------


class TestHybridSearchEngine:
    DIM = 32

    def _random_emb(self) -> np.ndarray:
        return np.random.randn(self.DIM).astype(np.float32)

    @pytest.fixture
    def engine(self, config: Config) -> HybridSearchEngine:
        return HybridSearchEngine(config, dimension=self.DIM)

    def test_add_and_search_sync(self, engine: HybridSearchEngine) -> None:
        engine.add_document("doc1", "the quick brown fox", self._random_emb())
        engine.add_document("doc2", "a lazy dog sleeps", self._random_emb())

        emb = self._random_emb()
        results = engine.search_sync("quick fox", emb, top_k=5)
        assert isinstance(results, list)
        assert len(results) >= 1
        assert all(isinstance(r, SearchResult) for r in results)

    @pytest.mark.anyio
    async def test_async_search(self, engine: HybridSearchEngine) -> None:
        engine.add_document("doc1", "machine learning algorithms", self._random_emb())
        engine.add_document("doc2", "web development frameworks", self._random_emb())

        emb = self._random_emb()
        results = await engine.search("machine learning", emb, top_k=5)
        assert len(results) >= 1
        assert results[0].doc_id in ("doc1", "doc2")

    def test_search_returns_snippets(self, engine: HybridSearchEngine) -> None:
        text = "Python is great for data science and machine learning applications."
        engine.add_document("doc1", text, self._random_emb())

        results = engine.search_sync("python data science", self._random_emb())
        assert len(results) >= 1
        if results[0].snippets:
            assert any("Python" in s.text or "data" in s.text for s in results[0].snippets)

    def test_delete_document(self, engine: HybridSearchEngine) -> None:
        engine.add_document("doc1", "test content", self._random_emb())
        assert engine.doc_count == 1

        engine.delete_document("doc1")
        # BM25 doc_count might not immediately reflect deletion in tantivy
        # but search should not return the deleted doc
        results = engine.search_sync("test content", self._random_emb())
        assert all(r.doc_id != "doc1" for r in results)

    def test_batch_add(self, engine: HybridSearchEngine) -> None:
        docs = [
            ("d1", "first document about cats", self._random_emb()),
            ("d2", "second document about dogs", self._random_emb()),
            ("d3", "third document about birds", self._random_emb()),
        ]
        engine.add_documents(docs)
        assert engine.doc_count >= 3

    def test_alpha_weighting(self, engine: HybridSearchEngine) -> None:
        engine.add_document("doc1", "exact keyword match test", self._random_emb())

        emb = self._random_emb()
        # BM25-heavy search
        r1 = engine.search_sync("exact keyword match", emb, alpha=0.0)
        # Dense-heavy search
        r2 = engine.search_sync("exact keyword match", emb, alpha=1.0)

        # Both should return results but potentially different scores
        assert len(r1) >= 1
        assert len(r2) >= 1

    def test_search_result_has_ranks(self, engine: HybridSearchEngine) -> None:
        engine.add_document("doc1", "quantum computing", self._random_emb())

        results = engine.search_sync("quantum computing", self._random_emb())
        assert len(results) >= 1
        # Should have at least a BM25 rank
        r = results[0]
        assert r.bm25_rank is not None or r.dense_rank is not None

    def test_empty_search(self, engine: HybridSearchEngine) -> None:
        results = engine.search_sync("anything", self._random_emb())
        assert results == []
