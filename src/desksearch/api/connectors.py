"""API endpoints for the connector system.

Provides REST endpoints for listing, enabling/disabling, configuring,
and syncing connectors.

These endpoints are mounted under ``/api/connectors/v2/`` to coexist
with the existing plugin-based connector endpoints at ``/api/connectors``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from desksearch.connectors import ConnectorRegistry

logger = logging.getLogger(__name__)

connector_router = APIRouter(prefix="/api/connectors/v2", tags=["connectors"])

# Module-level state, set at startup
_registry: ConnectorRegistry | None = None
_pipeline: Any = None  # IndexingPipeline


def set_connector_components(
    registry: ConnectorRegistry,
    pipeline: Any = None,
) -> None:
    """Inject the connector registry and pipeline at startup."""
    global _registry, _pipeline
    _registry = registry
    _pipeline = pipeline


def _get_registry() -> ConnectorRegistry:
    if _registry is None:
        raise HTTPException(status_code=503, detail="Connector registry not initialized")
    return _registry


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@connector_router.get("")
async def list_connectors() -> dict:
    """List all connectors with their current status."""
    reg = _get_registry()
    statuses = reg.list_status()
    return {"connectors": statuses, "total": len(statuses)}


@connector_router.get("/{name}")
async def get_connector(name: str) -> dict:
    """Get details for a specific connector."""
    reg = _get_registry()
    conn = reg.get(name)
    if conn is None:
        raise HTTPException(status_code=404, detail=f"Unknown connector: {name}")
    status = conn.status()
    status["name"] = conn.name
    status["description"] = conn.description
    return status


@connector_router.post("/{name}/enable")
async def enable_connector(name: str) -> dict:
    """Enable a connector."""
    reg = _get_registry()
    if not reg.enable(name):
        raise HTTPException(status_code=404, detail=f"Unknown connector: {name}")
    return {"status": "ok", "connector": name, "enabled": True}


@connector_router.post("/{name}/disable")
async def disable_connector(name: str) -> dict:
    """Disable a connector."""
    reg = _get_registry()
    if not reg.disable(name):
        raise HTTPException(status_code=404, detail=f"Unknown connector: {name}")
    return {"status": "ok", "connector": name, "enabled": False}


@connector_router.put("/{name}/config")
async def update_connector_config(name: str, body: dict) -> dict:
    """Update configuration for a connector."""
    reg = _get_registry()
    config = body.get("config", body)
    errors = reg.configure(name, config)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    conn = reg.get(name)
    return {
        "status": "ok",
        "connector": name,
        "config": conn._config if conn else {},
    }


@connector_router.post("/{name}/sync")
async def sync_connector(name: str) -> dict:
    """Trigger a manual sync for a connector."""
    reg = _get_registry()
    conn = reg.get(name)
    if conn is None:
        raise HTTPException(status_code=404, detail=f"Unknown connector: {name}")

    loop = asyncio.get_event_loop()
    docs, errors = await loop.run_in_executor(None, reg.sync, name)

    return {
        "status": "ok",
        "connector": name,
        "documents_found": len(docs),
        "errors": errors,
    }
