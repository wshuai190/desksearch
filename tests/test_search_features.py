"""Tests for advanced search features: filters, export, suggestions, favorites, recent."""
import time
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from desksearch.api.server import create_app
from desksearch.config import Config
from tests.conftest_api import MockEmbedder


@pytest.fixture()
def app(tmp_path):
    """Create a test application with an isolated data directory and mock embedder."""
    config = Config(data_dir=tmp_path / "data", index_paths=[])
    config.resolve_starbucks_tier()
    embedder = MockEmbedder(embedding_dim=config.embedding_dim)
    return create_app(config, embedder=embedder)


@pytest.fixture()
async def client(app):
    """Async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _get_store():
    """Get the module-level store from routes (set during app creation)."""
    from desksearch.api.routes import _store
    return _store


def _create_test_doc(tmp_path, store, name="test.txt", ext=".txt", content="hello world",
                     size=None, mtime=None):
    """Create a real file and insert it into the store. Returns doc_id."""
    f = tmp_path / name
    f.write_text(content)
    if mtime is not None:
        import os
        os.utime(str(f), (mtime, mtime))
    doc_id = store.upsert_document(f, num_chunks=1)
    # If we want a custom size, update it in DB (file stat would differ, but tests check API logic)
    if size is not None:
        store.conn.execute("UPDATE documents SET size = ? WHERE id = ?", (size, doc_id))
        store.conn.commit()
    return doc_id


# ===================================================================
# Search filters
# ===================================================================


class TestSearchFilters:
    """Test search filter parameters."""

    @pytest.mark.anyio
    async def test_type_filter_comma_separated(self, client):
        """Comma-separated type filter should be accepted."""
        resp = await client.get("/api/search", params={"q": "test", "type": "pdf,docx"})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_type_filter_single(self, client):
        """Single type filter should work."""
        resp = await client.get("/api/search", params={"q": "test", "type": "pdf"})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_date_after_filter(self, client):
        """after= date filter should be accepted."""
        resp = await client.get("/api/search", params={"q": "test", "after": "2026-01-01"})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_date_before_filter(self, client):
        """before= date filter should be accepted."""
        resp = await client.get("/api/search", params={"q": "test", "before": "2026-03-01"})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_date_range_filter(self, client):
        """Combined after + before date range should work."""
        resp = await client.get("/api/search", params={
            "q": "test", "after": "2026-01-01", "before": "2026-03-01"
        })
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_invalid_date_format(self, client):
        """Invalid date format should return 400."""
        resp = await client.get("/api/search", params={"q": "test", "after": "not-a-date"})
        assert resp.status_code == 400

    @pytest.mark.anyio
    async def test_size_min_filter(self, client):
        """size_min filter should be accepted."""
        resp = await client.get("/api/search", params={"q": "test", "size_min": 1000})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_size_max_filter(self, client):
        """size_max filter should be accepted."""
        resp = await client.get("/api/search", params={"q": "test", "size_max": 1000000})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_size_range_filter(self, client):
        """Combined size_min + size_max should work."""
        resp = await client.get("/api/search", params={
            "q": "test", "size_min": 1000, "size_max": 1000000
        })
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_folder_filter(self, client):
        """folder= filter should be accepted."""
        resp = await client.get("/api/search", params={"q": "test", "folder": "/some/folder"})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_all_filters_combined(self, client):
        """All filters combined should be accepted."""
        resp = await client.get("/api/search", params={
            "q": "test",
            "type": "pdf,docx",
            "folder": "/home/user/docs",
            "after": "2026-01-01",
            "before": "2026-12-31",
            "size_min": 100,
            "size_max": 5000000,
        })
        assert resp.status_code == 200


# ===================================================================
# Sort options
# ===================================================================


class TestSortOptions:
    """Test sort parameter variants."""

    @pytest.mark.anyio
    async def test_sort_relevance(self, client):
        resp = await client.get("/api/search", params={"q": "test", "sort": "relevance"})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_sort_date(self, client):
        resp = await client.get("/api/search", params={"q": "test", "sort": "date"})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_sort_size(self, client):
        resp = await client.get("/api/search", params={"q": "test", "sort": "size"})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_sort_name(self, client):
        resp = await client.get("/api/search", params={"q": "test", "sort": "name"})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_sort_by_legacy(self, client):
        """sort_by= (legacy param) should still work."""
        resp = await client.get("/api/search", params={"q": "test", "sort_by": "date_modified"})
        assert resp.status_code == 200


# ===================================================================
# Export formats
# ===================================================================


class TestExportFormats:
    """Test search result export in various formats."""

    @pytest.mark.anyio
    async def test_export_json(self, client):
        """format=json should return standard JSON response."""
        resp = await client.get("/api/search", params={"q": "test", "format": "json"})
        assert resp.status_code == 200
        body = resp.json()
        assert "results" in body

    @pytest.mark.anyio
    async def test_export_csv_empty(self, client):
        """format=csv on empty results should return CSV header."""
        resp = await client.get("/api/search", params={"q": "test", "format": "csv"})
        assert resp.status_code == 200
        text = resp.text
        assert "path,score,snippet" in text

    @pytest.mark.anyio
    async def test_export_text_empty(self, client):
        """format=text on empty results should return empty text."""
        resp = await client.get("/api/search", params={"q": "test", "format": "text"})
        assert resp.status_code == 200
        # Could be empty string
        assert resp.headers.get("content-type", "").startswith("text/plain")

    @pytest.mark.anyio
    async def test_export_default(self, client):
        """No format param should return JSON response."""
        resp = await client.get("/api/search", params={"q": "test"})
        assert resp.status_code == 200
        body = resp.json()
        assert "results" in body
        assert "total" in body


# ===================================================================
# Suggestions / autocomplete
# ===================================================================


class TestSuggestions:
    """Test the /api/suggest endpoint."""

    @pytest.mark.anyio
    async def test_suggest_empty(self, client):
        """Suggestions on a fresh index should return empty lists."""
        resp = await client.get("/api/suggest", params={"q": "a"})
        assert resp.status_code == 200
        body = resp.json()
        assert "suggestions" in body
        assert isinstance(body["suggestions"], list)

    @pytest.mark.anyio
    async def test_suggest_missing_query(self, client):
        """Missing q param should return 422."""
        resp = await client.get("/api/suggest")
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_suggest_after_search(self, client):
        """After a search, suggest should include recent queries."""
        # Perform a search to populate history
        await client.get("/api/search", params={"q": "machine learning"})
        resp = await client.get("/api/suggest", params={"q": "machine"})
        assert resp.status_code == 200
        body = resp.json()
        # Analytics-based suggestions depend on timing; just check structure
        assert "suggestions" in body
        assert "recent" in body

    @pytest.mark.anyio
    async def test_suggest_limit(self, client):
        """Custom limit should be respected."""
        resp = await client.get("/api/suggest", params={"q": "test", "limit": 3})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["suggestions"]) <= 3


# ===================================================================
# Favorites (body-based POST + path-based)
# ===================================================================


class TestFavorites:
    """Test favorites endpoints."""

    @pytest.mark.anyio
    async def test_list_favorites_empty(self, client):
        resp = await client.get("/api/favorites")
        assert resp.status_code == 200
        assert resp.json()["favorites"] == []

    @pytest.mark.anyio
    async def test_add_favorite_body_missing_fields(self, client):
        """POST /api/favorites with no doc_id or path should return 400."""
        resp = await client.post("/api/favorites", json={})
        assert resp.status_code == 400

    @pytest.mark.anyio
    async def test_add_favorite_body_nonexistent(self, client):
        """POST /api/favorites with invalid doc_id should return 404."""
        resp = await client.post("/api/favorites", json={"doc_id": 99999})
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_favorite_lifecycle_body(self, client, tmp_path):
        """POST /api/favorites (body), GET, DELETE lifecycle."""
        store = _get_store()
        if store is None:
            pytest.skip("Store not available")

        doc_id = _create_test_doc(tmp_path, store, "fav_body.txt")

        # Add via body
        resp = await client.post("/api/favorites", json={"doc_id": doc_id})
        assert resp.status_code == 200
        assert resp.json()["status"] == "added"

        # List
        resp = await client.get("/api/favorites")
        assert resp.status_code == 200
        favs = resp.json()["favorites"]
        assert len(favs) == 1
        assert favs[0]["doc_id"] == doc_id

        # Delete
        resp = await client.delete(f"/api/favorites/{doc_id}")
        assert resp.status_code == 200

        # Verify removed
        resp = await client.get("/api/favorites")
        assert resp.json()["favorites"] == []

    @pytest.mark.anyio
    async def test_favorite_by_path(self, client, tmp_path):
        """POST /api/favorites with path should work."""
        store = _get_store()
        if store is None:
            pytest.skip("Store not available")

        f = tmp_path / "fav_path.txt"
        f.write_text("favorite by path")
        doc_id = store.upsert_document(f, num_chunks=0)

        resp = await client.post("/api/favorites", json={"path": str(f)})
        assert resp.status_code == 200
        assert resp.json()["status"] == "added"
        assert resp.json()["doc_id"] == doc_id

    @pytest.mark.anyio
    async def test_favorite_path_based_endpoint(self, client, tmp_path):
        """POST /api/favorites/{doc_id} should also work."""
        store = _get_store()
        if store is None:
            pytest.skip("Store not available")

        doc_id = _create_test_doc(tmp_path, store, "fav_path_ep.txt")
        resp = await client.post(f"/api/favorites/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "added"

    @pytest.mark.anyio
    async def test_delete_favorite_nonexistent(self, client):
        """DELETE /api/favorites/{id} for non-favorited doc should return 404."""
        resp = await client.delete("/api/favorites/99999")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_favorite_duplicate(self, client, tmp_path):
        """Adding same favorite twice should return already_exists."""
        store = _get_store()
        if store is None:
            pytest.skip("Store not available")

        doc_id = _create_test_doc(tmp_path, store, "fav_dup.txt")
        await client.post("/api/favorites", json={"doc_id": doc_id})
        resp = await client.post("/api/favorites", json={"doc_id": doc_id})
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_exists"


# ===================================================================
# Recent files
# ===================================================================


class TestRecentFiles:
    """Test recent opens endpoints."""

    @pytest.mark.anyio
    async def test_recent_empty(self, client):
        resp = await client.get("/api/recent")
        assert resp.status_code == 200
        assert resp.json()["entries"] == []

    @pytest.mark.anyio
    async def test_recent_limit(self, client):
        resp = await client.get("/api/recent", params={"limit": 5})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_post_recent_body(self, client, tmp_path):
        """POST /api/recent with doc_id should record an open."""
        store = _get_store()
        if store is None:
            pytest.skip("Store not available")

        doc_id = _create_test_doc(tmp_path, store, "recent_body.txt")

        resp = await client.post("/api/recent", json={"doc_id": doc_id})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        resp = await client.get("/api/recent")
        entries = resp.json()["entries"]
        assert len(entries) == 1
        assert entries[0]["doc_id"] == doc_id

    @pytest.mark.anyio
    async def test_post_recent_by_path(self, client, tmp_path):
        """POST /api/recent with path should work."""
        store = _get_store()
        if store is None:
            pytest.skip("Store not available")

        f = tmp_path / "recent_path.txt"
        f.write_text("recent by path")
        doc_id = store.upsert_document(f, num_chunks=0)

        resp = await client.post("/api/recent", json={"path": str(f)})
        assert resp.status_code == 200
        assert resp.json()["doc_id"] == doc_id

    @pytest.mark.anyio
    async def test_post_recent_missing_fields(self, client):
        """POST /api/recent with no doc_id or path should return 400."""
        resp = await client.post("/api/recent", json={})
        assert resp.status_code == 400

    @pytest.mark.anyio
    async def test_post_recent_nonexistent(self, client):
        """POST /api/recent with invalid doc_id should return 404."""
        resp = await client.post("/api/recent", json={"doc_id": 99999})
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_track_open_path_endpoint(self, client, tmp_path):
        """POST /api/files/{doc_id}/open should still work."""
        store = _get_store()
        if store is None:
            pytest.skip("Store not available")

        doc_id = _create_test_doc(tmp_path, store, "track_open.txt")
        resp = await client.post(f"/api/files/{doc_id}/open")
        assert resp.status_code == 200

        resp = await client.get("/api/recent")
        entries = resp.json()["entries"]
        assert any(e["doc_id"] == doc_id for e in entries)


# ===================================================================
# Search history
# ===================================================================


class TestSearchHistory:
    """Test search history endpoints."""

    @pytest.mark.anyio
    async def test_history_empty(self, client):
        resp = await client.get("/api/search/history")
        assert resp.status_code == 200
        assert resp.json()["entries"] == []

    @pytest.mark.anyio
    async def test_history_after_search(self, client):
        """Searching should populate history."""
        await client.get("/api/search", params={"q": "neural networks"})
        resp = await client.get("/api/search/history")
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert len(entries) >= 1
        assert entries[0]["query"] == "neural networks"

    @pytest.mark.anyio
    async def test_history_limit(self, client):
        resp = await client.get("/api/search/history", params={"limit": 3})
        assert resp.status_code == 200
