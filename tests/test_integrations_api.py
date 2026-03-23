"""Tests for DeskSearch integration endpoints.

Covers:
- /api/v1/search  (external API + bearer-token auth)
- /api/alfred/search  (Alfred/Raycast JSON)
- /api/integrations/slack/search  (Slack slash command)
- /api/integrations/email/import  (mbox upload)
- /api/integrations/browser/sync  (browser bookmarks sync)
- /api/webhooks  (webhook CRUD)
- /api/webhooks/test  (webhook test-fire)
"""
from __future__ import annotations

import io
import json
import mailbox
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from desksearch.api.server import create_app
from desksearch.config import Config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path):
    config = Config(data_dir=tmp_path / "data")
    return create_app(config)


@pytest.fixture()
def app_with_key(tmp_path):
    config = Config(data_dir=tmp_path / "data", api_key="test-secret-key")
    return create_app(config)


@pytest.fixture()
def app_with_webhooks(tmp_path):
    config = Config(
        data_dir=tmp_path / "data",
        webhook_urls=["https://example.com/hook"],
    )
    return create_app(config)


@pytest.fixture()
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture()
async def auth_client(app_with_key):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_key),
        base_url="http://test",
        headers={"Authorization": "Bearer test-secret-key"},
    ) as ac:
        yield ac


@pytest.fixture()
async def webhook_client(app_with_webhooks):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_webhooks), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# /api/v1/search
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_v1_search_no_key_configured(client):
    """When no api_key is set, /api/v1/search is open."""
    resp = await client.get("/api/v1/search", params={"q": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert "total" in body
    assert "query_time_ms" in body


@pytest.mark.anyio
async def test_v1_search_with_correct_key(auth_client):
    """Correct bearer token passes auth."""
    resp = await auth_client.get("/api/v1/search", params={"q": "hello"})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_v1_search_wrong_key(app_with_key):
    """Wrong bearer token returns 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_key),
        base_url="http://test",
        headers={"Authorization": "Bearer wrong-key"},
    ) as client:
        resp = await client.get("/api/v1/search", params={"q": "hello"})
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_v1_search_no_token_when_key_required(app_with_key):
    """Missing Authorization header returns 401 when api_key is configured."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_key), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/search", params={"q": "hello"})
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_v1_search_missing_query(client):
    """Missing 'q' param returns 422."""
    resp = await client.get("/api/v1/search")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_v1_search_with_type_filter(client):
    """Type filter is accepted without error."""
    resp = await client.get("/api/v1/search", params={"q": "notes", "type": "md"})
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_v1_search_limit_clamped(client):
    """Limit > 100 should be rejected with 422."""
    resp = await client.get("/api/v1/search", params={"q": "x", "limit": 9999})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/alfred/search
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_alfred_search_returns_items(client):
    """Alfred endpoint always returns an 'items' list."""
    resp = await client.get("/api/alfred/search", params={"q": "test"})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)


@pytest.mark.anyio
async def test_alfred_search_empty_fallback(client):
    """Empty index returns a 'no results' fallback item (not an empty list)."""
    resp = await client.get("/api/alfred/search", params={"q": "xyzzy"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) >= 1
    assert body["items"][0]["uid"] == "no-results"


@pytest.mark.anyio
async def test_alfred_search_item_schema(client):
    """Alfred items have required fields when results exist."""
    # Empty index will give fallback — just check the response is valid JSON
    resp = await client.get("/api/alfred/search", params={"q": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    for item in body["items"]:
        assert "uid" in item
        assert "title" in item
        assert "subtitle" in item


# ---------------------------------------------------------------------------
# /api/integrations/slack/search
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_slack_search_empty_query(client):
    """Empty text → ephemeral usage message."""
    resp = await client.post(
        "/api/integrations/slack/search",
        data={"text": "", "command": "/ds", "user_name": "dylan"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["response_type"] == "ephemeral"
    assert "query" in body["text"].lower() or "Usage" in body["text"]


@pytest.mark.anyio
async def test_slack_search_no_results(client):
    """Query against empty index returns blocks with no-results message."""
    resp = await client.post(
        "/api/integrations/slack/search",
        data={"text": "quantum entanglement notebooks", "user_name": "dylan"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["response_type"] == "in_channel"
    assert "blocks" in body


@pytest.mark.anyio
async def test_slack_search_block_structure(client):
    """Response always contains the required Block Kit structure."""
    resp = await client.post(
        "/api/integrations/slack/search",
        data={"text": "test query"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "response_type" in body


# ---------------------------------------------------------------------------
# /api/integrations/email/import
# ---------------------------------------------------------------------------

def _make_mbox_bytes(*subjects: str) -> bytes:
    """Create a minimal mbox file in memory."""
    with tempfile.NamedTemporaryFile(suffix=".mbox", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        mbox = mailbox.mbox(str(tmp_path))
        for subject in subjects:
            msg = mailbox.mboxMessage()
            msg["From"] = "sender@example.com"
            msg["Subject"] = subject
            msg["Date"] = "Mon, 01 Jan 2024 00:00:00 +0000"
            msg.set_payload(f"Body of email: {subject}")
            mbox.add(msg)
        mbox.flush()
        mbox.close()
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


@pytest.mark.anyio
async def test_email_import_mbox(client):
    """Upload a valid .mbox file — should return 200 with count."""
    mbox_data = _make_mbox_bytes("Meeting Notes", "Project Update")
    resp = await client.post(
        "/api/integrations/email/import",
        files={"file": ("test.mbox", mbox_data, "application/mbox")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["emails_found"] >= 2
    assert "emails_indexed" in body


@pytest.mark.anyio
async def test_email_import_wrong_extension(client):
    """Non-.mbox/.eml file should be rejected with 400."""
    resp = await client.post(
        "/api/integrations/email/import",
        files={"file": ("archive.zip", b"fake", "application/zip")},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_email_import_eml(client, tmp_path):
    """Upload a valid .eml file — should be accepted."""
    eml_content = (
        "From: alice@example.com\r\n"
        "To: bob@example.com\r\n"
        "Subject: Test Email\r\n"
        "Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
        "Content-Type: text/plain\r\n"
        "\r\n"
        "Hello, this is a test email body.\r\n"
    ).encode()
    resp = await client.post(
        "/api/integrations/email/import",
        files={"file": ("test.eml", eml_content, "message/rfc822")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


# ---------------------------------------------------------------------------
# /api/integrations/browser/sync
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_browser_sync_no_browser(client):
    """Sync with no browser installed returns ok with zero bookmarks."""
    resp = await client.post("/api/integrations/browser/sync")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "bookmarks_found" in body


@pytest.mark.anyio
async def test_browser_sync_with_mock_bookmarks(client, tmp_path):
    """Sync with mocked bookmarks indexes them successfully."""
    from desksearch.plugins.base import Document

    mock_docs = [
        Document(
            id="bookmark:chrome:abc123",
            title="Google Scholar",
            content="Google Scholar\nhttps://scholar.google.com",
            source="chrome",
            metadata={"url": "https://scholar.google.com"},
        ),
        Document(
            id="bookmark:chrome:def456",
            title="arXiv",
            content="arXiv\nhttps://arxiv.org",
            source="chrome",
            metadata={"url": "https://arxiv.org"},
        ),
    ]

    with patch(
        "desksearch.plugins.builtin.browser_bookmarks.BrowserBookmarksConnector.fetch",
        return_value=mock_docs,
    ):
        resp = await client.post("/api/integrations/browser/sync")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["bookmarks_found"] == 2


# ---------------------------------------------------------------------------
# /api/webhooks
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_webhooks_empty(client):
    """Default config has no webhook URLs."""
    resp = await client.get("/api/webhooks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["webhook_urls"] == []
    assert body["count"] == 0


@pytest.mark.anyio
async def test_get_webhooks_populated(webhook_client):
    """Configured webhook URLs are returned."""
    resp = await webhook_client.get("/api/webhooks")
    assert resp.status_code == 200
    body = resp.json()
    assert "https://example.com/hook" in body["webhook_urls"]


@pytest.mark.anyio
async def test_put_webhooks(client):
    """PUT replaces the webhook URL list."""
    resp = await client.put(
        "/api/webhooks",
        json={"webhook_urls": ["https://hooks.example.com/notify"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "https://hooks.example.com/notify" in body["webhook_urls"]


@pytest.mark.anyio
async def test_put_webhooks_invalid_url(client):
    """Non-HTTP URLs are rejected."""
    resp = await client.put(
        "/api/webhooks",
        json={"webhook_urls": ["ftp://bad.example.com"]},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_put_webhooks_clear(client):
    """Empty list clears all webhooks."""
    # First add one
    await client.put("/api/webhooks", json={"webhook_urls": ["https://x.com"]})
    # Then clear
    resp = await client.put("/api/webhooks", json={"webhook_urls": []})
    assert resp.status_code == 200
    assert resp.json()["webhook_urls"] == []


# ---------------------------------------------------------------------------
# /api/webhooks/test
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_webhook_test_missing_url(client):
    """Missing url field returns 400."""
    resp = await client.post("/api/webhooks/test", json={})
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_webhook_test_invalid_url(client):
    """Non-HTTP URL returns 400."""
    resp = await client.post("/api/webhooks/test", json={"url": "not-a-url"})
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_webhook_test_success(client):
    """Mock HTTP delivery succeeds."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("desksearch.api.integrations.httpx.AsyncClient") as mock_client_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_ctx

        resp = await client.post(
            "/api/webhooks/test",
            json={"url": "https://example.com/webhook"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["delivered"] is True


@pytest.mark.anyio
async def test_webhook_test_delivery_failure(client):
    """Network failure returns 502."""
    with patch("desksearch.api.integrations.httpx.AsyncClient") as mock_client_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_cls.return_value = mock_ctx

        resp = await client.post(
            "/api/webhooks/test",
            json={"url": "https://unreachable.example.com/hook"},
        )

    assert resp.status_code == 502
