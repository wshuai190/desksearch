"""Memory usage utilities for DeskSearch.

Provides lightweight helpers for logging and tracking process memory,
backed by psutil when available (falls back to a no-op).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import psutil as _psutil  # noqa: F401
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


def rss_mb() -> Optional[float]:
    """Return the current process RSS in megabytes, or None if psutil unavailable."""
    if not _PSUTIL_AVAILABLE:
        return None
    import psutil
    return psutil.Process(os.getpid()).memory_info().rss / 1_048_576


def log_memory(label: str = "") -> Optional[float]:
    """Log the current process RSS and return it in MB.

    Args:
        label: Short description of where in the code this is called from.

    Returns:
        RSS in megabytes, or None if psutil is not installed.
    """
    mb = rss_mb()
    if mb is not None:
        logger.info("Memory [%s]: %.1f MB RSS", label or "checkpoint", mb)
    return mb


def log_memory_delta(before_mb: Optional[float], label: str = "") -> Optional[float]:
    """Log the change in RSS since *before_mb* was captured.

    Args:
        before_mb: RSS snapshot taken before the operation (from ``log_memory``
            or ``rss_mb``).  If None the delta cannot be computed.
        label: Short description of the operation being measured.

    Returns:
        Current RSS in MB, or None.
    """
    after_mb = rss_mb()
    if after_mb is None:
        return None
    if before_mb is not None:
        delta = after_mb - before_mb
        sign = "+" if delta >= 0 else ""
        logger.info(
            "Memory [%s]: %.1f MB RSS (%s%.1f MB delta)",
            label or "checkpoint", after_mb, sign, delta,
        )
    else:
        logger.info("Memory [%s]: %.1f MB RSS", label or "checkpoint", after_mb)
    return after_mb
