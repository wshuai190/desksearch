"""Connector for importing Slack workspace exports.

Slack exports produce a ZIP archive (or directory) with JSON files
organised by channel and date.  This connector parses messages, resolves
usernames, and yields ``Document`` objects per channel-day.
"""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from pathlib import Path
from typing import Any, Iterator, Optional

from desksearch.connectors.base import Connector
from desksearch.plugins.base import Document

logger = logging.getLogger(__name__)


class SlackExportConnector(Connector):
    """Import and index messages from a Slack workspace export."""

    @property
    def name(self) -> str:
        return "slack-export"

    @property
    def description(self) -> str:
        return "Import messages from a Slack workspace export (ZIP or directory)."

    def __init__(self) -> None:
        super().__init__()
        self._export_path: Path | None = None
        self._include_bots: bool = False
        self._users: dict[str, str] = {}
        self._channels: dict[str, str] = {}

    def configure(self, config: dict[str, Any]) -> None:
        if "export_path" in config:
            self._export_path = Path(config["export_path"]).expanduser().resolve()
        self._include_bots = config.get("include_bots", False)
        self._config = config

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        if "export_path" in config:
            p = Path(config["export_path"]).expanduser().resolve()
            if not p.exists():
                errors.append(f"Export path not found: {config['export_path']}")
        return errors

    def fetch(self) -> Iterator[Document]:
        if self._export_path is None:
            logger.warning("SlackExportConnector: no export_path configured")
            return
        if not self._export_path.exists():
            logger.warning("Slack export not found: %s", self._export_path)
            return

        export_dir = self._resolve_export_dir()
        if export_dir is None:
            return

        self._load_users(export_dir)
        self._load_channels(export_dir)

        for channel_dir in sorted(export_dir.iterdir()):
            if not channel_dir.is_dir():
                continue
            channel_name = channel_dir.name
            for json_file in sorted(channel_dir.glob("*.json")):
                doc = self._parse_day_file(json_file, channel_name)
                if doc is not None:
                    yield doc

    def schedule(self) -> Optional[str]:
        # No auto-schedule — Slack exports are one-time imports
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_export_dir(self) -> Path | None:
        """Handle ZIP archives by extracting them; return the directory."""
        assert self._export_path is not None

        if self._export_path.is_file() and self._export_path.suffix == ".zip":
            extract_to = self._export_path.parent / self._export_path.stem
            if not extract_to.exists():
                try:
                    with zipfile.ZipFile(self._export_path, "r") as zf:
                        zf.extractall(extract_to)
                except Exception:
                    logger.exception("Failed to extract Slack export ZIP")
                    return None
            return extract_to

        if self._export_path.is_dir():
            return self._export_path

        logger.warning("Slack export path is not a directory or ZIP: %s", self._export_path)
        return None

    def _parse_day_file(
        self, json_file: Path, channel_name: str
    ) -> Document | None:
        """Parse a single day's message JSON file into a Document."""
        try:
            messages = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Failed to parse %s", json_file)
            return None

        if not isinstance(messages, list):
            return None

        day_texts: list[str] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            if not self._include_bots and msg.get("subtype") == "bot_message":
                continue
            text = msg.get("text", "").strip()
            if not text:
                continue
            user_id = msg.get("user", "")
            username = self._users.get(user_id, user_id)
            ts = msg.get("ts", "")
            day_texts.append(f"[{username}] {text}")

        if not day_texts:
            return None

        date_str = json_file.stem
        content = "\n".join(day_texts)
        title = f"#{channel_name} — {date_str}"
        uid = hashlib.sha256(f"{channel_name}:{date_str}".encode()).hexdigest()[:16]

        return Document(
            id=f"slack:{uid}",
            title=title,
            content=content,
            source=f"slack:#{channel_name}",
            metadata={
                "channel": channel_name,
                "date": date_str,
                "message_count": len(day_texts),
            },
        )

    def _load_users(self, export_dir: Path) -> None:
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
