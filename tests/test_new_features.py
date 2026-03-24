"""Tests for new features: collections, duplicates, analytics, onboarding, etc.

Covers edge cases and empty-index behavior for all new API endpoints.
"""
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from desksearch.api.server import create_app
from desksearch.config import Config
from tests.conftest_api import MockEmbedder


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DIM = 32


@pytest.fixture()
def app(tmp_path):
    config = Config(data_dir=tmp_path / "data", index_paths=[])
    config.resolve_starbucks_tier()
    embedder = MockEmbedder(embedding_dim=config.embedding_dim)
    return create_app(config, embedder=embedder)


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Dashboard — empty index
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_dashboard_empty_index(client):
    """GET /api/dashboard with empty index returns zeros, not crash."""
    resp = await client.get("/api/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_documents"] == 0
    assert body["total_chunks"] == 0
    assert body["is_indexing"] is False
    assert body["type_breakdown"] == {}
    assert isinstance(body["watched_folders"], list)


@pytest.mark.anyio
async def test_dashboard_response_structure(client):
    """Dashboard response has all expected fields."""
    resp = await client.get("/api/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    expected_keys = {"total_documents", "total_chunks", "index_size_mb",
                     "is_indexing", "type_breakdown", "watched_folders"}
    assert expected_keys.issubset(set(body.keys()))


# ---------------------------------------------------------------------------
# Collections — empty / small index
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_collections_empty_index(client):
    """GET /api/collections with empty index returns empty, not crash."""
    resp = await client.get("/api/collections")
    assert resp.status_code == 200
    body = resp.json()
    assert body["topics"] == []
    assert body["total_docs_clustered"] == 0


@pytest.mark.anyio
async def test_collections_response_structure(client):
    """Collections response has expected fields."""
    resp = await client.get("/api/collections")
    assert resp.status_code == 200
    body = resp.json()
    assert "topics" in body
    assert "total_docs_clustered" in body


@pytest.mark.anyio
async def test_collections_with_n_topics_param(client):
    """Collections endpoint accepts n_topics parameter."""
    resp = await client.get("/api/collections", params={"n_topics": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["topics"] == []  # empty index


@pytest.mark.anyio
async def test_collections_invalid_n_topics(client):
    """n_topics < 2 should return 422."""
    resp = await client.get("/api/collections", params={"n_topics": 1})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_collections_n_topics_too_large(client):
    """n_topics > 20 should return 422."""
    resp = await client.get("/api/collections", params={"n_topics": 25})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Duplicates — empty / small index
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_duplicates_empty_index(client):
    """GET /api/duplicates with empty index returns empty, not crash."""
    resp = await client.get("/api/duplicates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pairs"] == []
    assert body["total"] == 0


@pytest.mark.anyio
async def test_duplicates_response_structure(client):
    """Duplicates response has expected fields."""
    resp = await client.get("/api/duplicates")
    assert resp.status_code == 200
    body = resp.json()
    assert "pairs" in body
    assert "total" in body


@pytest.mark.anyio
async def test_duplicates_threshold_param(client):
    """Duplicates endpoint accepts threshold parameter."""
    resp = await client.get("/api/duplicates", params={"threshold": 0.95})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_duplicates_invalid_threshold_too_low(client):
    """Threshold < 0.5 should return 422."""
    resp = await client.get("/api/duplicates", params={"threshold": 0.1})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_duplicates_invalid_threshold_too_high(client):
    """Threshold >= 1.0 should return 422."""
    resp = await client.get("/api/duplicates", params={"threshold": 1.0})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Analytics — empty
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_analytics_empty(client):
    """GET /api/analytics with 0 searches returns zeros, not crash."""
    resp = await client.get("/api/analytics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_searches"] == 0
    assert body["total_clicks"] == 0
    assert body["top_searches"] == []
    assert body["top_files"] == []
    assert body["search_over_time"] == []


@pytest.mark.anyio
async def test_analytics_response_structure(client):
    """Analytics response has all expected fields."""
    resp = await client.get("/api/analytics")
    assert resp.status_code == 200
    body = resp.json()
    expected_keys = {"total_searches", "total_clicks", "top_searches",
                     "top_files", "search_over_time"}
    assert expected_keys.issubset(set(body.keys()))


@pytest.mark.anyio
async def test_analytics_days_param(client):
    """Analytics endpoint accepts days parameter."""
    resp = await client.get("/api/analytics", params={"days": 7})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_analytics_click_tracking(client):
    """POST /api/analytics/click should return ok."""
    resp = await client.post(
        "/api/analytics/click",
        json={"query": "test", "path": "/tmp/file.txt", "filename": "file.txt"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.anyio
async def test_analytics_click_empty_body(client):
    """POST /api/analytics/click with empty fields still returns ok (best effort)."""
    resp = await client.post("/api/analytics/click", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Suggest / Autocomplete — empty
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_suggest_empty_index(client):
    """GET /api/suggest with empty index returns empty suggestions."""
    resp = await client.get("/api/suggest", params={"q": "test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["suggestions"] == []
    assert body["recent"] == []


@pytest.mark.anyio
async def test_suggest_response_structure(client):
    """Suggest response has expected fields."""
    resp = await client.get("/api/suggest", params={"q": "a"})
    assert resp.status_code == 200
    body = resp.json()
    assert "suggestions" in body
    assert "recent" in body


@pytest.mark.anyio
async def test_suggest_missing_query(client):
    """GET /api/suggest without q returns 422."""
    resp = await client.get("/api/suggest")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_suggest_limit_param(client):
    """Suggest endpoint accepts custom limit."""
    resp = await client.get("/api/suggest", params={"q": "x", "limit": 3})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_health_returns_correct_structure(client):
    """GET /api/health returns correct structure with all components."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert body["status"] in ("healthy", "degraded", "unhealthy")
    assert "search_mode" in body
    assert "is_indexing" in body
    assert "components" in body
    components = body["components"]
    assert "sqlite" in components
    assert "bm25" in components
    assert "faiss" in components
    assert "embedder" in components


@pytest.mark.anyio
async def test_health_always_returns_200(client):
    """Health endpoint never raises — always 200."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Memory endpoint
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_memory_endpoint(client):
    """GET /api/memory returns process info."""
    resp = await client.get("/api/memory")
    assert resp.status_code == 200
    body = resp.json()
    assert "process" in body
    assert "pid" in body["process"]
    assert "rss_mb" in body["process"]
    assert "model" in body
    assert "indexes" in body


@pytest.mark.anyio
async def test_memory_endpoint_structure(client):
    """Memory endpoint response has all expected nested fields."""
    resp = await client.get("/api/memory")
    assert resp.status_code == 200
    body = resp.json()
    # Process info
    assert "active_threads" in body["process"]
    # Model info
    assert "loaded" in body["model"]
    assert "name" in body["model"]
    # Indexes info
    assert "dense_vectors" in body["indexes"]
    assert "bm25_documents" in body["indexes"]
    assert "store_documents" in body["indexes"]
    assert "store_chunks" in body["indexes"]


# ---------------------------------------------------------------------------
# Onboarding endpoints
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_onboarding_status(client):
    """GET /api/onboarding/status returns valid structure."""
    resp = await client.get("/api/onboarding/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "needs_setup" in body
    assert "has_indexed_documents" in body
    assert isinstance(body["needs_setup"], bool)
    assert isinstance(body["has_indexed_documents"], bool)


@pytest.mark.anyio
async def test_onboarding_detect_folders(client):
    """GET /api/onboarding/detect-folders returns a list of folders."""
    resp = await client.get("/api/onboarding/detect-folders")
    assert resp.status_code == 200
    body = resp.json()
    assert "folders" in body
    assert isinstance(body["folders"], list)


@pytest.mark.anyio
async def test_onboarding_setup_no_paths(client):
    """POST /api/onboarding/setup with no paths returns 400."""
    resp = await client.post("/api/onboarding/setup", json={"paths": []})
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_onboarding_setup_invalid_paths(client):
    """POST /api/onboarding/setup with non-existent paths returns 400."""
    resp = await client.post(
        "/api/onboarding/setup",
        json={"paths": ["/absolutely/nonexistent/path/xyz"]},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_onboarding_setup_valid_path(client, tmp_path):
    """POST /api/onboarding/setup with a valid path succeeds."""
    test_dir = tmp_path / "test_folder"
    test_dir.mkdir()
    resp = await client.post(
        "/api/onboarding/setup",
        json={"paths": [str(test_dir)], "start_indexing": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert str(test_dir) in body["paths"]


# ---------------------------------------------------------------------------
# Folders endpoints
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_folders_empty(client):
    """GET /api/folders with no config returns empty list."""
    resp = await client.get("/api/folders")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


@pytest.mark.anyio
async def test_add_folder_nonexistent(client):
    """POST /api/folders with bad path returns 400."""
    resp = await client.post(
        "/api/folders",
        json={"path": "/nonexistent/path/xyz123"},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_add_folder_valid(client, tmp_path):
    """POST /api/folders with valid dir succeeds."""
    test_dir = tmp_path / "watch_me"
    test_dir.mkdir()
    resp = await client.post("/api/folders", json={"path": str(test_dir)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == str(test_dir)
    assert body["status"] == "watching"


@pytest.mark.anyio
async def test_add_folder_duplicate(client, tmp_path):
    """Adding the same folder twice returns 400."""
    test_dir = tmp_path / "watch_dup"
    test_dir.mkdir()
    resp1 = await client.post("/api/folders", json={"path": str(test_dir)})
    assert resp1.status_code == 200
    resp2 = await client.post("/api/folders", json={"path": str(test_dir)})
    assert resp2.status_code == 400


@pytest.mark.anyio
async def test_remove_folder_not_watched(client):
    """DELETE /api/folders/... for non-watched folder returns 404."""
    resp = await client.delete("/api/folders/nonexistent/path")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Files endpoints — empty index
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_files_empty(client):
    """GET /api/files with empty index returns empty list."""
    resp = await client.get("/api/files")
    assert resp.status_code == 200
    body = resp.json()
    assert body["files"] == []
    assert body["total"] == 0


@pytest.mark.anyio
async def test_list_files_pagination_params(client):
    """GET /api/files accepts pagination params."""
    resp = await client.get("/api/files", params={"page": 1, "page_size": 10})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_list_files_sort_params(client):
    """GET /api/files accepts sort params."""
    resp = await client.get("/api/files", params={"sort_by": "filename", "sort_dir": "asc"})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_file_preview_not_found(client):
    """GET /api/files/<id>/preview with bad ID returns 404."""
    resp = await client.get("/api/files/99999/preview")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_delete_file_not_found(client):
    """DELETE /api/files/<id> with bad ID returns 404."""
    resp = await client.delete("/api/files/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Activity — empty index
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_activity_empty(client):
    """GET /api/activity with empty index returns empty entries."""
    resp = await client.get("/api/activity")
    assert resp.status_code == 200
    body = resp.json()
    assert body["entries"] == []


@pytest.mark.anyio
async def test_activity_limit_param(client):
    """GET /api/activity accepts limit param."""
    resp = await client.get("/api/activity", params={"limit": 5})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Related docs — empty index
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_related_docs_not_found(client):
    """GET /api/related/<id> with bad ID returns 404."""
    resp = await client.get("/api/related/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Rich preview — empty index
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_rich_preview_not_found(client):
    """GET /api/preview/<id> with bad ID returns 404."""
    resp = await client.get("/api/preview/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Browse directories
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_browse_directories_home(client):
    """GET /api/browse-directories returns dirs from home."""
    resp = await client.get("/api/browse-directories")
    assert resp.status_code == 200
    body = resp.json()
    assert "current" in body
    assert "directories" in body
    assert isinstance(body["directories"], list)


@pytest.mark.anyio
async def test_browse_directories_specific_path(client, tmp_path):
    """GET /api/browse-directories with specific path."""
    sub = tmp_path / "subdir"
    sub.mkdir()
    resp = await client.get("/api/browse-directories", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["current"] == str(tmp_path)
    dir_names = [d["name"] for d in body["directories"]]
    assert "subdir" in dir_names


@pytest.mark.anyio
async def test_browse_directories_invalid_path(client):
    """GET /api/browse-directories with invalid path returns 400."""
    resp = await client.get("/api/browse-directories", params={"path": "/nonexistent/xyz"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Settings edge cases
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_settings_update_file_extensions(client, monkeypatch):
    """PUT /api/settings with file_extensions updates correctly."""
    monkeypatch.setattr(Config, "save", lambda self, path=None: None)
    resp = await client.put(
        "/api/settings",
        json={"file_extensions": [".txt", ".md", ".pdf"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert ".txt" in body["file_extensions"]


@pytest.mark.anyio
async def test_settings_update_excluded_dirs(client, monkeypatch):
    """PUT /api/settings with excluded_dirs updates correctly."""
    monkeypatch.setattr(Config, "save", lambda self, path=None: None)
    resp = await client.put(
        "/api/settings",
        json={"excluded_dirs": ["node_modules", ".git", "__pycache__"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "node_modules" in body["excluded_dirs"]


# ---------------------------------------------------------------------------
# API key endpoints
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_regenerate_api_key(client, monkeypatch):
    """POST /api/v1/api-key/regenerate returns a new key."""
    monkeypatch.setattr(Config, "save", lambda self, path=None: None)
    resp = await client.post("/api/v1/api-key/regenerate")
    assert resp.status_code == 200
    body = resp.json()
    assert "api_key" in body
    assert body["api_key"].startswith("ds-")


@pytest.mark.anyio
async def test_clear_api_key(client, monkeypatch):
    """DELETE /api/v1/api-key clears the key."""
    monkeypatch.setattr(Config, "save", lambda self, path=None: None)
    resp = await client.delete("/api/v1/api-key")
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key"] is None
    assert body["status"] == "ok"


# ---------------------------------------------------------------------------
# Clear index
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_clear_index_empty(client):
    """DELETE /api/index/clear on empty index returns ok."""
    resp = await client.delete("/api/index/clear")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["documents_removed"] == 0
    assert body["chunks_removed"] == 0


# ---------------------------------------------------------------------------
# Analytics store unit tests
# ---------------------------------------------------------------------------


class TestAnalyticsStore:
    """Unit tests for AnalyticsStore."""

    def test_empty_store_totals(self, tmp_path):
        from desksearch.core.analytics import AnalyticsStore
        store = AnalyticsStore(tmp_path / "analytics.db")
        assert store.total_searches() == 0
        assert store.total_clicks() == 0

    def test_record_and_retrieve_search(self, tmp_path):
        from desksearch.core.analytics import AnalyticsStore
        store = AnalyticsStore(tmp_path / "analytics.db")
        store.record_search("machine learning", result_count=5)
        assert store.total_searches() == 1
        recent = store.get_recent_searches(limit=10)
        assert "machine learning" in recent

    def test_record_click(self, tmp_path):
        from desksearch.core.analytics import AnalyticsStore
        store = AnalyticsStore(tmp_path / "analytics.db")
        store.record_click("test query", "/tmp/file.txt", "file.txt")
        assert store.total_clicks() == 1

    def test_suggest_from_recent(self, tmp_path):
        from desksearch.core.analytics import AnalyticsStore
        store = AnalyticsStore(tmp_path / "analytics.db")
        store.record_search("python programming", result_count=3)
        store.record_search("pytorch tutorial", result_count=2)
        store.record_search("java basics", result_count=1)
        suggestions = store.suggest_from_recent("py", limit=5)
        assert len(suggestions) >= 1
        assert all("py" in s.lower() for s in suggestions)

    def test_top_searches(self, tmp_path):
        from desksearch.core.analytics import AnalyticsStore
        store = AnalyticsStore(tmp_path / "analytics.db")
        for _ in range(5):
            store.record_search("popular query", result_count=10)
        for _ in range(2):
            store.record_search("less popular", result_count=5)
        top = store.top_searches(limit=5)
        assert len(top) == 2
        assert top[0]["query"] == "popular query"
        assert top[0]["count"] == 5

    def test_search_frequency_over_time(self, tmp_path):
        from desksearch.core.analytics import AnalyticsStore
        store = AnalyticsStore(tmp_path / "analytics.db")
        store.record_search("test", result_count=1)
        freq = store.search_frequency_over_time(days=7)
        assert len(freq) >= 1
        assert "date" in freq[0]
        assert "count" in freq[0]

    def test_ignore_very_short_queries(self, tmp_path):
        from desksearch.core.analytics import AnalyticsStore
        store = AnalyticsStore(tmp_path / "analytics.db")
        store.record_search("a")  # too short, should be ignored
        assert store.total_searches() == 0

    def test_top_clicked_files(self, tmp_path):
        from desksearch.core.analytics import AnalyticsStore
        store = AnalyticsStore(tmp_path / "analytics.db")
        for _ in range(3):
            store.record_click("query", "/tmp/popular.txt", "popular.txt")
        store.record_click("query", "/tmp/other.txt", "other.txt")
        top = store.top_clicked_files(limit=5)
        assert len(top) == 2
        assert top[0]["clicks"] == 3


# ---------------------------------------------------------------------------
# Collections / duplicates unit tests
# ---------------------------------------------------------------------------


class TestCollectionsUnit:
    """Unit tests for collection and duplicate detection functions."""

    def test_cluster_documents_too_few_docs(self):
        """Clustering with < 4 docs should return empty (need MIN_DOCS_PER_TOPIC * 2)."""
        from desksearch.core.collections import cluster_documents
        doc_embs = {1: np.random.rand(DIM).astype(np.float32)}
        result = cluster_documents(doc_embs, {1: "/a"}, {1: "a.txt"})
        assert result == []

    def test_cluster_documents_enough_docs(self):
        """Clustering with sufficient docs should return topics."""
        from desksearch.core.collections import cluster_documents
        n = 20
        doc_embs = {i: np.random.rand(DIM).astype(np.float32) for i in range(n)}
        doc_paths = {i: f"/path/doc{i}.txt" for i in range(n)}
        doc_fnames = {i: f"doc{i}.txt" for i in range(n)}
        result = cluster_documents(doc_embs, doc_paths, doc_fnames, n_clusters=3)
        assert len(result) > 0
        total_docs = sum(len(t.doc_ids) for t in result)
        assert total_docs == n

    def test_find_duplicates_empty(self):
        """find_duplicates with < 2 docs returns empty."""
        from desksearch.core.collections import find_duplicates
        result = find_duplicates({1: np.random.rand(DIM).astype(np.float32)}, {}, {})
        assert result == []

    def test_find_duplicates_identical_vectors(self):
        """Identical vectors should be detected as duplicates."""
        from desksearch.core.collections import find_duplicates
        vec = np.random.rand(DIM).astype(np.float32)
        doc_embs = {1: vec.copy(), 2: vec.copy()}
        doc_paths = {1: "/a/file1.txt", 2: "/b/file2.txt"}
        doc_fnames = {1: "file1.txt", 2: "file2.txt"}
        result = find_duplicates(doc_embs, doc_paths, doc_fnames, threshold=0.9)
        assert len(result) == 1
        assert result[0]["similarity"] > 0.99

    def test_find_related_docs_not_in_index(self):
        """find_related_docs for unknown doc_id returns empty."""
        from desksearch.core.collections import find_related_docs
        doc_embs = {1: np.random.rand(DIM).astype(np.float32)}
        result = find_related_docs(999, doc_embs, {}, {})
        assert result == []

    def test_find_related_docs_returns_results(self):
        """find_related_docs should return similar documents."""
        from desksearch.core.collections import find_related_docs
        base = np.random.rand(DIM).astype(np.float32)
        doc_embs = {
            1: base,
            2: base + np.random.rand(DIM).astype(np.float32) * 0.01,  # very similar
            3: np.random.rand(DIM).astype(np.float32),  # random
        }
        doc_paths = {1: "/a", 2: "/b", 3: "/c"}
        doc_fnames = {1: "a.txt", 2: "b.txt", 3: "c.txt"}
        result = find_related_docs(1, doc_embs, doc_paths, doc_fnames, top_k=2)
        assert len(result) >= 1
        # The very similar doc should be first
        assert result[0]["doc_id"] == 2


# ---------------------------------------------------------------------------
# Onboarding unit tests
# ---------------------------------------------------------------------------


class TestOnboardingUnit:
    """Unit tests for onboarding module."""

    def test_detect_folders_returns_dict(self):
        from desksearch.onboarding import detect_folders
        result = detect_folders()
        assert isinstance(result, dict)
        assert "documents" in result
        assert "developer" in result
        assert "notes" in result

    def test_is_first_run_with_no_config(self, tmp_path, monkeypatch):
        """is_first_run returns True when no config file exists."""
        from desksearch.onboarding import is_first_run
        import desksearch.onboarding as onboarding_mod
        monkeypatch.setattr(onboarding_mod, "DEFAULT_DATA_DIR", tmp_path / "nonexistent")
        assert is_first_run() is True


# ---------------------------------------------------------------------------
# Memory utility tests
# ---------------------------------------------------------------------------


class TestMemoryUtils:
    """Tests for memory utility functions."""

    def test_rss_mb_returns_float_or_none(self):
        from desksearch.utils.memory import rss_mb
        result = rss_mb()
        assert result is None or isinstance(result, float)

    def test_log_memory_returns_float_or_none(self):
        from desksearch.utils.memory import log_memory
        result = log_memory("test")
        assert result is None or isinstance(result, float)

    def test_log_memory_delta(self):
        from desksearch.utils.memory import log_memory_delta
        result = log_memory_delta(100.0, "test")
        assert result is None or isinstance(result, float)


# ---------------------------------------------------------------------------
# Search edge cases
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_search_very_long_query(client):
    """Search with a very long query should not crash."""
    long_query = "a" * 1000
    resp = await client.get("/api/search", params={"q": long_query})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_search_special_characters(client):
    """Search with special characters should not crash."""
    resp = await client.get("/api/search", params={"q": "hello & world | (test)"})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_search_unicode_query(client):
    """Search with unicode characters should not crash."""
    resp = await client.get("/api/search", params={"q": "机器学习 NLP"})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_search_with_rich_false(client):
    """Search with rich=false should work."""
    resp = await client.get("/api/search", params={"q": "test", "rich": "false"})
    assert resp.status_code == 200
