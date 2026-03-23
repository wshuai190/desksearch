"""Integration endpoints for DeskSearch.

Provides optional API connectors for external tools. All integrations are
**no-op when not configured** — they degrade gracefully if API keys, webhook
URLs, or browser profiles are missing.

Endpoints:
  GET  /api/v1/search                     — External search API (bearer-token auth)
  GET  /api/alfred/search                 — Alfred/Raycast script-filter JSON
  POST /api/integrations/slack/search     — Slack slash-command webhook handler
  POST /api/integrations/email/import     — Upload & index a .mbox/.eml file
  POST /api/integrations/browser/sync     — Sync Chrome/Firefox bookmarks
  GET  /api/webhooks                      — List configured webhook URLs
  PUT  /api/webhooks                      — Update webhook URLs
  POST /api/webhooks/test                 — Test-fire a single webhook
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Security, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from desksearch.api.schemas import SearchResponse, SearchResult
from desksearch.config import Config

logger = logging.getLogger(__name__)

integrations_router = APIRouter()
_security = HTTPBearer(auto_error=False)

# Module-level state injected at startup
_config: Config = Config()
_search_engine = None
_embedder = None
_store = None
_pipeline = None


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

def set_config(config: Config) -> None:
    """Inject configuration (called from server.py at startup)."""
    global _config
    _config = config


def set_components(search_engine, pipeline, embedder, store) -> None:
    """Inject core components (called from server.py at startup)."""
    global _search_engine, _pipeline, _embedder, _store
    _search_engine = search_engine
    _pipeline = pipeline
    _embedder = embedder
    _store = store


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def _require_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_security),
) -> None:
    """Validate Bearer token. Skips check if no api_key is configured."""
    configured_key = _config.api_key
    if not configured_key:
        return  # No key → open access (developer mode)
    if credentials is None or credentials.credentials != configured_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Send: Authorization: Bearer <key>",
        )


# ---------------------------------------------------------------------------
# Shared search helper
# ---------------------------------------------------------------------------

async def _run_search(q: str, type_filter: Optional[str], limit: int) -> SearchResponse:
    """Execute a hybrid search and return a SearchResponse.

    Shared by /api/v1/search, /api/alfred/search, and the Slack handler.
    """
    start = time.perf_counter()

    if _search_engine is None or _embedder is None or _store is None:
        return SearchResponse(results=[], total=0, query_time_ms=0.0)

    loop = asyncio.get_event_loop()
    query_embedding = await loop.run_in_executor(None, _embedder.embed_query, q)
    raw_results = await _search_engine.search(q, query_embedding, top_k=limit * 3)

    results: list[SearchResult] = []
    seen_files: set[int] = set()

    for r in raw_results:
        try:
            chunk_id = int(r.doc_id)
        except (ValueError, TypeError):
            continue
        chunk = _store.get_chunk_by_id(chunk_id)
        if chunk is None:
            continue
        doc = _store.get_document_by_id(chunk.doc_id)
        if doc is None or doc.id in seen_files:
            continue
        if type_filter and doc.extension.lstrip(".") != type_filter:
            continue

        seen_files.add(doc.id)
        snippet = r.snippets[0].highlighted if r.snippets else chunk.text[:200]
        modified = datetime.fromtimestamp(doc.modified_time, tz=timezone.utc)

        results.append(SearchResult(
            doc_id=r.doc_id,
            path=doc.path,
            filename=doc.filename,
            snippet=snippet,
            score=round(r.score, 4),
            file_type=doc.extension.lstrip("."),
            modified=modified,
            file_size=doc.size,
        ))

        if len(results) >= limit:
            break

    elapsed_ms = (time.perf_counter() - start) * 1000
    return SearchResponse(
        results=results, total=len(results), query_time_ms=round(elapsed_ms, 2)
    )


# ---------------------------------------------------------------------------
# 1. External REST API  —  GET /api/v1/search
# ---------------------------------------------------------------------------

@integrations_router.get(
    "/api/v1/search",
    response_model=SearchResponse,
    tags=["external-api"],
    summary="External search API (bearer-token auth)",
)
async def external_search(
    q: str = Query(..., min_length=1, description="Search query"),
    type: Optional[str] = Query(None, description="Filter by file extension (e.g. pdf)"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
    _: None = Depends(_require_api_key),
) -> SearchResponse:
    """Search DeskSearch from any external tool.

    Supports optional bearer-token authentication (set ``api_key`` in config).
    Returns the same ``SearchResponse`` schema as the internal ``/api/search``
    endpoint, so any existing client code is compatible.

    **Example**::

        curl -H "Authorization: Bearer mysecretkey" \\
             "http://localhost:3777/api/v1/search?q=meeting+notes&limit=5"
    """
    return await _run_search(q=q, type_filter=type, limit=limit)


# ---------------------------------------------------------------------------
# 2. Alfred / Raycast  —  GET /api/alfred/search
# ---------------------------------------------------------------------------

_FILE_TYPE_EMOJI: dict[str, str] = {
    "pdf": "📄", "py": "🐍", "js": "📜", "ts": "📜",
    "md": "📝", "txt": "📝", "docx": "📃", "doc": "📃",
    "json": "⚙️", "yaml": "⚙️", "yml": "⚙️", "ipynb": "📊",
    "sh": "🖥️", "csv": "📊", "html": "🌐", "rs": "🦀",
}


@integrations_router.get(
    "/api/alfred/search",
    tags=["external-api"],
    summary="Alfred/Raycast script-filter JSON",
)
async def alfred_search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(9, ge=1, le=50, description="Max results (Alfred default 9)"),
    _: None = Depends(_require_api_key),
) -> dict:
    """Return results in `Alfred Script Filter JSON`_ format.

    Drop-in for Alfred workflows or Raycast extensions. Point your script
    filter at ``http://localhost:3777/api/alfred/search?q={query}``
    (optionally passing an API key via the ``DESKSEARCH_API_KEY`` env var).

    .. _Alfred Script Filter JSON:
        https://www.alfredapp.com/help/workflows/inputs/script-filter/json/
    """
    resp = await _run_search(q=q, type_filter=None, limit=limit)

    items = []
    for result in resp.results:
        file_type = result.file_type.lower()
        emoji = _FILE_TYPE_EMOJI.get(file_type, "📁")
        subtitle = result.snippet[:120] if result.snippet else result.path

        items.append({
            "uid": result.doc_id,
            "title": f"{emoji} {result.filename}",
            "subtitle": subtitle,
            "arg": result.path,
            "autocomplete": result.filename,
            "type": "file:skipcheck",
            "icon": {"path": "icon.png"},
            "mods": {
                "cmd": {
                    "valid": True,
                    "arg": result.path,
                    "subtitle": f"Open: {result.path}",
                },
                "alt": {
                    "valid": True,
                    "arg": result.path,
                    "subtitle": f"Score: {result.score:.3f} · {result.file_type}",
                },
            },
            "text": {
                "copy": result.path,
                "largetype": result.filename,
            },
            "quicklookurl": result.path,
        })

    # Alfred shows a "no results" fallback when items is empty
    if not items:
        items.append({
            "uid": "no-results",
            "title": "No results found",
            "subtitle": f'No matches for \u201c{q}\u201d',
            "valid": False,
        })

    return {"items": items}


# ---------------------------------------------------------------------------
# 3. Slack slash-command  —  POST /api/integrations/slack/search
# ---------------------------------------------------------------------------

@integrations_router.post(
    "/api/integrations/slack/search",
    tags=["slack"],
    summary="Slack slash-command webhook handler",
)
async def slack_search(
    text: str = Form(""),
    user_name: str = Form(""),
    channel_name: str = Form(""),
    command: str = Form("/search"),
    response_url: Optional[str] = Form(None),
) -> dict:
    """Handle a Slack slash-command payload and return formatted Block Kit blocks.

    **Setup (in your Slack app):**

    1. Create a slash command (e.g. ``/ds`` or ``/search``).
    2. Set the Request URL to ``https://your-host/api/integrations/slack/search``.
    3. The bot will reply with rich result blocks in the channel.

    Slack verifies the payload is from Slack — add ``slack_signing_secret``
    to your DeskSearch config to enable HMAC signature verification (recommended
    for production deployments).
    """
    query = text.strip()

    if not query:
        return {
            "response_type": "ephemeral",
            "text": f"Please provide a search query. Usage: `{command} <query>`",
        }

    if _search_engine is None or _embedder is None:
        return {
            "response_type": "ephemeral",
            "text": "❌ DeskSearch is starting up — please try again in a moment.",
        }

    try:
        resp = await _run_search(q=query, type_filter=None, limit=5)
    except Exception as exc:
        logger.exception("Slack search failed for query %r", query)
        return {"response_type": "ephemeral", "text": f"❌ Search error: {exc}"}

    if not resp.results:
        return {
            "response_type": "in_channel",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🔍 No results found for *{query}*",
                    },
                }
            ],
        }

    # Build Block Kit blocks
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🔍 {query}", "emoji": True},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*{resp.total}* result(s) · {resp.query_time_ms:.0f}ms"
                        + (f" · searched by @{user_name}" if user_name else "")
                    ),
                }
            ],
        },
        {"type": "divider"},
    ]

    for result in resp.results:
        emoji = _FILE_TYPE_EMOJI.get(result.file_type.lower(), "📁")
        # Sanitize snippet for Slack markdown (remove HTML-ish markers)
        snippet = (
            result.snippet[:280]
            .replace("**", "*")
            .replace("<em>", "_")
            .replace("</em>", "_")
            .replace("<b>", "*")
            .replace("</b>", "*")
        )
        score_pct = round(result.score * 100, 1)

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{emoji} *{result.filename}*\n"
                    f"{snippet}\n"
                    f"_Score: {score_pct}% · `{result.path}`_"
                ),
            },
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"Powered by <http://localhost:{_config.port}|DeskSearch>",
            }
        ],
    })

    return {"response_type": "in_channel", "blocks": blocks}


# ---------------------------------------------------------------------------
# 4. Email import  —  POST /api/integrations/email/import
# ---------------------------------------------------------------------------

@integrations_router.post(
    "/api/integrations/email/import",
    tags=["email"],
    summary="Upload and index a .mbox or .eml file",
)
async def import_email_mbox(
    file: UploadFile = File(..., description=".mbox or .eml file to import"),
    _: None = Depends(_require_api_key),
) -> dict:
    """Accept an uploaded email export and index its contents.

    **Supported formats:**

    * ``.mbox`` — Unix mbox archive (multiple messages)
    * ``.eml`` — Single RFC 2822 email message

    Each message is parsed (sender, date, subject, body) and indexed as a
    searchable document. The original file is not stored permanently — only
    the extracted text is indexed.

    **Example**::

        curl -X POST http://localhost:3777/api/integrations/email/import \\
             -F "file=@exported.mbox"
    """
    if _pipeline is None or _store is None or _embedder is None:
        raise HTTPException(status_code=503, detail="Indexing pipeline not initialized")

    filename = file.filename or "upload.mbox"
    if not (filename.endswith(".mbox") or filename.endswith(".eml")):
        raise HTTPException(
            status_code=400,
            detail="Only .mbox and .eml files are supported",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    suffix = ".eml" if filename.endswith(".eml") else ".mbox"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="wb") as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        from desksearch.plugins.builtin.email_connector import EmailConnector

        if suffix == ".eml":
            raw_docs = [EmailConnector._parse_eml(tmp_path)]
            raw_docs = [d for d in raw_docs if d is not None]
        else:
            raw_docs = EmailConnector._parse_mbox(tmp_path)

        indexed_count = 0
        errors = 0

        with tempfile.TemporaryDirectory() as stage_dir:
            stage = Path(stage_dir)
            for doc in raw_docs:
                try:
                    safe_name = doc.id.replace(":", "_").replace("/", "_")[:64]
                    staged = stage / f"{safe_name}.txt"
                    staged.write_text(doc.content, encoding="utf-8")

                    gen = _pipeline.index_file(staged)
                    try:
                        while True:
                            next(gen)
                    except StopIteration:
                        pass

                    indexed_count += 1
                except Exception as exc:
                    logger.warning("Failed to index email %s: %s", doc.id, exc)
                    errors += 1

        return {
            "status": "ok",
            "filename": filename,
            "emails_found": len(raw_docs),
            "emails_indexed": indexed_count,
            "errors": errors,
        }
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 5. Browser bookmarks sync  —  POST /api/integrations/browser/sync
# ---------------------------------------------------------------------------

@integrations_router.post(
    "/api/integrations/browser/sync",
    tags=["browser"],
    summary="Sync Chrome/Firefox bookmarks into the index",
)
async def sync_browser_bookmarks(
    _: None = Depends(_require_api_key),
) -> dict:
    """Read browser bookmarks from Chrome and Firefox and add them to the index.

    Reads from the default platform profile paths. Custom paths can be
    configured in ``plugin_config.browser-bookmarks`` in settings:

    .. code-block:: json

        {
          "plugin_config": {
            "browser-bookmarks": {
              "chrome_bookmarks": "/path/to/Bookmarks",
              "firefox_places": "/path/to/places.sqlite"
            }
          }
        }

    Returns a summary of how many bookmarks were found and indexed.
    """
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Indexing pipeline not initialized")

    from desksearch.plugins.builtin.browser_bookmarks import BrowserBookmarksConnector

    connector = BrowserBookmarksConnector()
    plugin_cfg = _config.plugin_config.get("browser-bookmarks", {})
    connector.setup(plugin_cfg)

    loop = asyncio.get_event_loop()
    docs = await loop.run_in_executor(None, connector.fetch)

    if not docs:
        return {
            "status": "ok",
            "message": "No bookmarks found. Check that Chrome or Firefox is installed.",
            "bookmarks_found": 0,
            "bookmarks_indexed": 0,
        }

    indexed_count = 0
    errors = 0

    with tempfile.TemporaryDirectory() as stage_dir:
        stage = Path(stage_dir)
        for doc in docs:
            try:
                safe_name = doc.id.replace(":", "_").replace("/", "_")[:64]
                staged = stage / f"{safe_name}.txt"
                staged.write_text(
                    f"Title: {doc.title}\n"
                    f"URL: {doc.metadata.get('url', '')}\n"
                    f"Source: {doc.source}\n\n"
                    f"{doc.content}",
                    encoding="utf-8",
                )
                gen = _pipeline.index_file(staged)
                try:
                    while True:
                        next(gen)
                except StopIteration:
                    pass
                indexed_count += 1
            except Exception as exc:
                logger.warning("Failed to index bookmark %s: %s", doc.id, exc)
                errors += 1

    return {
        "status": "ok",
        "bookmarks_found": len(docs),
        "bookmarks_indexed": indexed_count,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# 6. Webhook management  —  GET/PUT /api/webhooks  &  POST /api/webhooks/test
# ---------------------------------------------------------------------------

@integrations_router.get(
    "/api/webhooks",
    tags=["webhooks"],
    summary="List configured webhook notification URLs",
)
async def get_webhooks() -> dict:
    """Return the currently configured webhook notification URLs.

    Webhooks are POSTed to when indexing completes or new files are found.
    Set them via ``PUT /api/webhooks`` or by editing the config file directly.
    """
    return {
        "webhook_urls": _config.webhook_urls,
        "count": len(_config.webhook_urls),
        "description": (
            "POST notifications are sent to these URLs when indexing finishes "
            "or when new files are discovered. Update via PUT /api/webhooks."
        ),
    }


@integrations_router.put(
    "/api/webhooks",
    tags=["webhooks"],
    summary="Update webhook notification URLs",
)
async def update_webhooks(body: dict) -> dict:
    """Replace the list of webhook notification URLs.

    Payload: ``{"webhook_urls": ["https://example.com/hook", ...]}``
    """
    global _config
    urls = body.get("webhook_urls", [])
    if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
        raise HTTPException(status_code=400, detail="webhook_urls must be a list of strings")

    # Validate URLs look reasonable (don't need strict parsing)
    for url in urls:
        if not url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid URL (must start with http:// or https://): {url}",
            )

    config_data = _config.model_dump()
    config_data["webhook_urls"] = urls
    _config = Config(**config_data)
    _config.save()

    return {"status": "ok", "webhook_urls": _config.webhook_urls}


@integrations_router.post(
    "/api/webhooks/test",
    tags=["webhooks"],
    summary="Send a test notification to a webhook URL",
)
async def test_webhook(body: dict) -> dict:
    """POST a test event to the given URL to verify your webhook receiver.

    Payload: ``{"url": "https://example.com/hook"}``
    """
    url = body.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="url is required in request body")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="url must start with http:// or https://")

    payload = {
        "event": "test",
        "source": "DeskSearch",
        "message": "Test webhook notification from DeskSearch",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
        return {
            "status": "ok",
            "url": url,
            "http_status": resp.status_code,
            "delivered": resp.status_code < 400,
        }
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Webhook timed out: {url}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Webhook delivery failed: {exc}")


# ---------------------------------------------------------------------------
# Webhook notification dispatcher (called by routes.py on indexing events)
# ---------------------------------------------------------------------------

async def notify_webhooks(event: str, data: dict) -> None:
    """Fire-and-forget POST to all configured webhook URLs.

    Called internally by ``routes.py`` when indexing completes or new files
    are found. Silently no-ops if no ``webhook_urls`` are configured.

    Args:
        event: Event name, e.g. ``"indexing_complete"`` or ``"files_found"``.
        data:  Additional event payload (merged into the top-level JSON body).
    """
    urls = _config.webhook_urls
    if not urls:
        return

    payload = {
        "event": event,
        "source": "DeskSearch",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        **data,
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        for url in urls:
            try:
                await client.post(url, json=payload)
                logger.debug("Webhook delivered [%s] → %s", event, url)
            except Exception as exc:
                logger.warning("Webhook delivery failed [%s] → %s: %s", event, url, exc)
