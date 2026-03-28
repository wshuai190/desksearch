"""Connector for importing .mbox (and .eml) email files.

Uses Python's ``mailbox`` and ``email`` stdlib to parse messages, extracting
subject, from, to, date, and body text.  Each email becomes a ``Document``
with rich metadata.
"""

from __future__ import annotations

import email
import email.policy
import hashlib
import logging
import mailbox as mbox_mod
from pathlib import Path
from typing import Any, Iterator, Optional

from desksearch.connectors.base import Connector
from desksearch.plugins.base import Document

logger = logging.getLogger(__name__)


class EmailMboxConnector(Connector):
    """Import and index emails from .mbox and .eml files."""

    @property
    def name(self) -> str:
        return "email-mbox"

    @property
    def description(self) -> str:
        return "Import emails from .mbox and .eml files, extracting subject, sender, date, and body."

    def __init__(self) -> None:
        super().__init__()
        self._directories: list[Path] = []

    def configure(self, config: dict[str, Any]) -> None:
        raw_dirs = config.get("directories", [])
        self._directories = [Path(d).expanduser().resolve() for d in raw_dirs]
        self._config = config

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        for d in config.get("directories", []):
            p = Path(d).expanduser().resolve()
            if not p.is_dir():
                errors.append(f"Email directory not found: {d}")
        return errors

    def fetch(self) -> Iterator[Document]:
        for directory in self._directories:
            if not directory.is_dir():
                logger.warning("Email directory not found: %s", directory)
                continue

            # .eml files
            for path in directory.rglob("*.eml"):
                doc = self._parse_eml(path)
                if doc is not None:
                    yield doc

            # .mbox files
            for path in directory.rglob("*.mbox"):
                yield from self._parse_mbox(path)

    def schedule(self) -> Optional[str]:
        return "0 */12 * * *" if self._directories else None

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(msg: email.message.Message) -> str:
        """Extract plain text from an email message."""
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
    def _msg_to_document(
        cls, msg: email.message.Message, source: str
    ) -> Document | None:
        """Convert an email.message.Message to a Document."""
        body = cls._extract_text(msg)
        if not body.strip():
            return None

        subject = msg.get("Subject", "(no subject)")
        sender = msg.get("From", "")
        to = msg.get("To", "")
        date = msg.get("Date", "")

        header = f"From: {sender}\nTo: {to}\nDate: {date}\nSubject: {subject}\n\n"
        content = header + body

        doc_id = hashlib.sha256(content.encode()).hexdigest()[:16]
        return Document(
            id=f"email:{doc_id}",
            title=subject,
            content=content,
            source=source,
            metadata={
                "from": sender,
                "to": to,
                "date": date,
                "subject": subject,
            },
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
    def _parse_mbox(cls, path: Path) -> Iterator[Document]:
        try:
            mbox = mbox_mod.mbox(str(path))
            for msg in mbox:
                doc = cls._msg_to_document(msg, str(path))
                if doc is not None:
                    yield doc
        except Exception:
            logger.exception("Failed to parse .mbox: %s", path)
