"""Environment compatibility shims applied on ``import desksearch``.

These exist because a few upstream libraries build proxy matcher objects
from ``NO_PROXY`` at client-construction time and raise on entries they
cannot parse. The failure happens inside a third-party library, far away
from anything DeskSearch controls, so we normalise the value once here.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_NO_PROXY_VARS = ("NO_PROXY", "no_proxy")


def sanitize_no_proxy() -> str | None:
    """Drop ``NO_PROXY`` entries that break proxy-matcher construction.

    Entries containing a square bracket (typically IPv6 literals such as
    ``[::1]`` that Docker Desktop and some VPN clients write on Windows)
    are turned into an unparsable wildcard pattern by ``httpx``-based
    clients, which then raise::

        InvalidURL: Invalid port: ':1]'

    Because ``huggingface_hub`` builds such a client before *every* model
    download, a single bracketed entry makes embedding models impossible to
    fetch. Plain ``::1`` / ``127.0.0.1`` / ``localhost`` entries are kept, so
    loopback traffic still bypasses the proxy.

    Returns the cleaned value when a change was made, otherwise ``None``.
    """
    for var in _NO_PROXY_VARS:
        raw = os.environ.get(var)
        if not raw or "[" not in raw:
            continue

        kept = [part for part in raw.split(",") if part.strip() and "[" not in part]
        cleaned = ",".join(kept)
        os.environ[var] = cleaned
        logger.debug("Sanitised %s: dropped bracketed IPv6 entries", var)
        return cleaned

    return None
