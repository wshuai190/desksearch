"""Connector plugin for indexing .eml and .mbox email files."""

from __future__ import annotations

import email
import email.policy
import hashlib
import logging
import mailbox
from pathlib import Path
from typing import Any

from desksearch.plugins.base import BaseConnectorPlugin, Document

logger = logging.getLogger(__name__)


class EmailConnector(BaseConnectorPlugin):
    """Index local email files (.eml and .mbox)."""

    name = "email-connector"
    version = "0.1.0"
    author = "DeskSearch"
    description = "Index .eml and .mbox email files from configured directories."

    def __init__(self) -> None:
        self._directories: list[Path] = []

    def setup(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        raw_dirs = config.get("directories", [])
        self._directories = [Path(d).expanduser() for d in raw_dirs]

    # ------------------------------------------------------------------

    def fetch(self) -> list[Document]:
        docs: list[Document] = []
        for directory in self._directories:
            if not directory.is_dir():
                logger.warning("Email directory not found: %s", directory)
                continue
            for path in directory.rglob("*.eml"):
                doc = self._parse_eml(path)
                if doc:
                    docs.append(doc)
            for path in directory.rglob("*.mbox"):
                docs.extend(self._parse_mbox(path))
        return docs

    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(msg: email.message.Message) -> str:
        parts: list[str] = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode("utf-8", errors="replace"))
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                parts.append(payload.decode("utf-8", errors="replace"))
        return "\n".join(parts)

    @classmethod
    def _msg_to_document(cls, msg: email.message.Message, source: str) -> Document | None:
        body = cls._extract_text(msg)
        if not body.strip():
            return None
        subject = msg.get("Subject", "(no subject)")
        sender = msg.get("From", "")
        date = msg.get("Date", "")
        header = f"From: {sender}\nDate: {date}\nSubject: {subject}\n\n"
        content = header + body
        doc_id = hashlib.sha256(content.encode()).hexdigest()[:16]
        return Document(
            id=f"email:{doc_id}",
            title=subject,
            content=content,
            source=source,
            metadata={"from": sender, "date": date},
        )

    @classmethod
    def _parse_eml(cls, path: Path) -> Document | None:
        try:
            raw = path.read_bytes()
            msg = email.message_from_bytes(raw, policy=email.policy.default)
            return cls._msg_to_document(msg, str(path))
        except Exception:
            logger.exception("Failed to parse .eml: %s", path)
            return None

    @classmethod
    def _parse_mbox(cls, path: Path) -> list[Document]:
        docs: list[Document] = []
        try:
            mbox = mailbox.mbox(str(path))
            for msg in mbox:
                doc = cls._msg_to_document(msg, str(path))
                if doc:
                    docs.append(doc)
        except Exception:
            logger.exception("Failed to parse .mbox: %s", path)
        return docs
