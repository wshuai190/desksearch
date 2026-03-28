"""Connector plugin for indexing Slack workspace exports.

Slack exports (from workspace admin → Export Data) produce a ZIP archive
containing JSON files organised by channel and date:

    export/
      channels.json          — channel metadata
      users.json             — user metadata
      #general/
        2024-01-01.json      — messages for that date
        2024-01-02.json
      #random/
        ...

This connector reads the extracted export directory, parses messages, and
produces ``Document`` objects suitable for indexing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from pathlib import Path
from typing import Any

from desksearch.plugins.base import BaseConnectorPlugin, Document

logger = logging.getLogger(__name__)


class SlackExportConnector(BaseConnectorPlugin):
    """Index messages from a Slack workspace export."""

    name = "slack-export"
    version = "0.1.0"
    author = "DeskSearch"
    description = "Import and index messages from a Slack workspace export (ZIP or directory)."

    def __init__(self) -> None:
        self._export_path: Path | None = None
        self._include_bots: bool = False
        self._users: dict[str, str] = {}   # user_id → display_name
        self._channels: dict[str, str] = {}  # channel_id → channel_name

    def setup(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        if "export_path" in config:
            self._export_path = Path(config["export_path"]).expanduser().resolve()
        self._include_bots = config.get("include_bots", False)

    # ------------------------------------------------------------------

    def fetch(self) -> list[Document]:
        if self._export_path is None:
            logger.warning("SlackExportConnector: no export_path configured")
            return []

        if not self._export_path.exists():
            logger.warning("Slack export not found: %s", self._export_path)
            return []

        # Handle ZIP archives — extract to a temp dir alongside the zip
        export_dir = self._export_path
        extracted = False
        if self._export_path.is_file() and self._export_path.suffix == ".zip":
            export_dir = self._export_path.parent / self._export_path.stem
            if not export_dir.exists():
                try:
                    with zipfile.ZipFile(self._export_path, "r") as zf:
                        zf.extractall(export_dir)
                    extracted = True
                except Exception:
                    logger.exception("Failed to extract Slack export ZIP")
                    return []

        if not export_dir.is_dir():
            logger.warning("Slack export directory not found: %s", export_dir)
            return []

        # Load user mapping
        self._load_users(export_dir)
        self._load_channels(export_dir)

        docs: list[Document] = []

        # Walk channel directories
        for channel_dir in sorted(export_dir.iterdir()):
            if not channel_dir.is_dir():
                continue
            channel_name = channel_dir.name
            for json_file in sorted(channel_dir.glob("*.json")):
                try:
                    messages = json.loads(json_file.read_text(encoding="utf-8"))
                except Exception:
                    logger.warning("Failed to parse %s", json_file)
                    continue

                if not isinstance(messages, list):
                    continue

                # Group messages into conversation chunks for better searchability
                day_texts: list[str] = []
                for msg in messages:
                    if not isinstance(msg, dict):
                        continue
                    # Skip bot messages unless configured
                    if not self._include_bots and msg.get("subtype") == "bot_message":
                        continue
                    text = msg.get("text", "").strip()
                    if not text:
                        continue
                    user_id = msg.get("user", "")
                    username = self._users.get(user_id, user_id)
                    day_texts.append(f"[{username}]: {text}")

                if day_texts:
                    date_str = json_file.stem  # e.g. "2024-01-01"
                    content = "\n".join(day_texts)
                    title = f"#{channel_name} — {date_str}"
                    uid = hashlib.sha256(
                        f"{channel_name}:{date_str}".encode()
                    ).hexdigest()[:16]

                    docs.append(Document(
                        id=f"slack:{uid}",
                        title=title,
                        content=content,
                        source=f"slack:#{channel_name}",
                        metadata={
                            "channel": channel_name,
                            "date": date_str,
                            "message_count": len(day_texts),
                        },
                    ))

        logger.info(
            "SlackExportConnector: found %d day-channel documents from %s",
            len(docs), export_dir,
        )
        return docs

    # ------------------------------------------------------------------

    def _load_users(self, export_dir: Path) -> None:
        """Load user id → name mapping from users.json."""
        users_file = export_dir / "users.json"
        if not users_file.exists():
            return
        try:
            users = json.loads(users_file.read_text(encoding="utf-8"))
            for u in users:
                uid = u.get("id", "")
                name = (
                    u.get("profile", {}).get("display_name")
                    or u.get("real_name")
                    or u.get("name")
                    or uid
                )
                self._users[uid] = name
        except Exception:
            logger.warning("Failed to parse users.json")

    def _load_channels(self, export_dir: Path) -> None:
        """Load channel metadata from channels.json."""
        channels_file = export_dir / "channels.json"
        if not channels_file.exists():
            return
        try:
            channels = json.loads(channels_file.read_text(encoding="utf-8"))
            for ch in channels:
                cid = ch.get("id", "")
                name = ch.get("name", cid)
                self._channels[cid] = name
        except Exception:
            logger.warning("Failed to parse channels.json")
