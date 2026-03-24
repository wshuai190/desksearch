"""Tests for the DeskSearch API server."""
import pytest
from httpx import ASGITransport, AsyncClient

from desksearch.api.server import create_app
from desksearch.config import Config
from desksearch.indexer.embedder import Embedder
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


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_search_empty_index(client):
    """Searching an empty index should return zero results, not an error."""
    resp = await client.get("/api/search", params={"q": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []
    assert body["total"] == 0
    assert "query_time_ms" in body


@pytest.mark.anyio
async def test_search_missing_query(client):
    """A search without a query parameter should return 422."""
    resp = await client.get("/api/search")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_search_with_type_filter(client):
    """Type filter param should be accepted without error."""
    resp = await client.get("/api/search", params={"q": "test", "type": "pdf"})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_search_limit(client):
    """Custom limit should be accepted."""
    resp = await client.get("/api/search", params={"q": "test", "limit": 5})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_index_invalid_path(client):
    """Indexing a non-existent path should return 400."""
    resp = await client.post(
        "/api/index", json={"paths": ["/nonexistent/path/abc123"]}
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_index_valid_path(client, tmp_path):
    """Indexing an existing directory should return 200 with indexing=True."""
    resp = await client.post("/api/index", json={"paths": [str(tmp_path)]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_indexing"] is True


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_status(client):
    """Status endpoint should return valid IndexStatus."""
    resp = await client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_documents" in body
    assert "is_indexing" in body


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_settings(client):
    """GET /api/settings should return the current config."""
    resp = await client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert "data_dir" in body
    assert "embedding_model" in body
    assert "file_extensions" in body


@pytest.mark.anyio
async def test_update_settings(client, tmp_path, monkeypatch):
    """PUT /api/settings should accept partial updates."""
    # Monkey-patch save so it doesn't write to the real home dir
    monkeypatch.setattr(Config, "save", lambda self, path=None: None)

    resp = await client.put("/api/settings", json={"chunk_size": 256})
    assert resp.status_code == 200
    body = resp.json()
    assert body["chunk_size"] == 256


@pytest.mark.anyio
async def test_update_settings_empty(client):
    """PUT /api/settings with no fields should return 400."""
    resp = await client.put("/api/settings", json={})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Open file
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_open_file_not_found(client):
    """Opening a non-existent file should return 404."""
    resp = await client.get("/api/open/nonexistent_file.txt")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_open_file_exists(client, tmp_path, monkeypatch):
    """Opening an existing file should return 200."""
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello")

    # Prevent actually opening a file during tests
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: None)

    resp = await client.get(f"/api/open/{test_file}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Search sort_by and folder filter
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_search_sort_by_param(client):
    """sort_by param should be accepted."""
    resp = await client.get("/api/search", params={"q": "test", "sort_by": "date_modified"})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_search_sort_by_file_size(client):
    """sort_by=file_size should be accepted."""
    resp = await client.get("/api/search", params={"q": "test", "sort_by": "file_size"})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_search_sort_by_file_type(client):
    """sort_by=file_type should be accepted."""
    resp = await client.get("/api/search", params={"q": "test", "sort_by": "file_type"})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_search_folder_filter(client):
    """folder param should be accepted without error."""
    resp = await client.get("/api/search", params={"q": "test", "folder": "/some/folder"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Search History
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_search_history_empty(client):
    """Search history should return empty list initially."""
    resp = await client.get("/api/search/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["entries"] == []


@pytest.mark.anyio
async def test_search_history_populated(client):
    """After searching, history should contain the query."""
    await client.get("/api/search", params={"q": "hello world"})
    resp = await client.get("/api/search/history")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["entries"]) >= 1
    assert body["entries"][0]["query"] == "hello world"


@pytest.mark.anyio
async def test_search_history_limit(client):
    """Search history should respect the limit parameter."""
    resp = await client.get("/api/search/history", params={"limit": 5})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_favorites_list_empty(client):
    """Favorites list should be empty initially."""
    resp = await client.get("/api/favorites")
    assert resp.status_code == 200
    body = resp.json()
    assert body["favorites"] == []


@pytest.mark.anyio
async def test_favorite_nonexistent_doc(client):
    """Favoriting a nonexistent doc should return 404."""
    resp = await client.post("/api/favorites/99999")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_unfavorite_nonexistent(client):
    """Unfavoriting something not in favorites should return 404."""
    resp = await client.delete("/api/favorites/99999")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_favorite_add_and_remove(client, tmp_path):
    """Full favorite lifecycle: add, list, remove."""
    # First, index a file so we have a doc_id
    from desksearch.api.routes import _store
    if _store is None:
        pytest.skip("Store not available")

    # Create a test file and manually insert a document
    test_file = tmp_path / "fav_test.txt"
    test_file.write_text("favorite test content")
    doc_id = _store.upsert_document(test_file, num_chunks=0)

    # Add favorite
    resp = await client.post(f"/api/favorites/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "added"

    # Adding again should say already_exists
    resp = await client.post(f"/api/favorites/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "already_exists"

    # List favorites
    resp = await client.get("/api/favorites")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["favorites"]) == 1
    assert body["favorites"][0]["doc_id"] == doc_id

    # Remove favorite
    resp = await client.delete(f"/api/favorites/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "removed"

    # List should be empty again
    resp = await client.get("/api/favorites")
    assert resp.status_code == 200
    assert resp.json()["favorites"] == []


# ---------------------------------------------------------------------------
# Recent Opens
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recent_opens_empty(client):
    """Recent opens should be empty initially."""
    resp = await client.get("/api/recent")
    assert resp.status_code == 200
    body = resp.json()
    assert body["entries"] == []


@pytest.mark.anyio
async def test_track_open_nonexistent(client):
    """Tracking open for a nonexistent doc should return 404."""
    resp = await client.post("/api/files/99999/open")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_track_open_and_list(client, tmp_path):
    """Track a file open and verify it appears in recent."""
    from desksearch.api.routes import _store
    if _store is None:
        pytest.skip("Store not available")

    test_file = tmp_path / "recent_test.txt"
    test_file.write_text("recent test content")
    doc_id = _store.upsert_document(test_file, num_chunks=0)

    # Track open
    resp = await client.post(f"/api/files/{doc_id}/open")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # List recent
    resp = await client.get("/api/recent")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["doc_id"] == doc_id
