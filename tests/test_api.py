"""Tests for the DeskSearch API server."""
import pytest
from httpx import ASGITransport, AsyncClient

from desksearch.api.server import create_app
from desksearch.config import Config


@pytest.fixture()
def app(tmp_path):
    """Create a test application with an isolated data directory."""
    config = Config(data_dir=tmp_path / "data")
    return create_app(config)


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
