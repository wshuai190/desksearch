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


def current_rss_mb() -> float:
    """Return the current process RSS in megabytes on every supported platform.

    Unlike :func:`rss_mb` this never returns ``None``: it degrades through
    psutil -> /proc (Linux) -> ``resource.getrusage`` (POSIX only, guarded
    because the module does not exist on Windows) -> ``0.0``.
    """
    mb = rss_mb()
    if mb is not None:
        return mb

    # Linux: read the kernel's own accounting of this process.
    try:
        with open(f"/proc/{os.getpid()}/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except Exception:
        pass

    # POSIX fallback. Imported lazily: `resource` is not available on Windows.
    try:
        import sys

        import resource  # type: ignore[import-not-found]

        ru = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is bytes on macOS, kilobytes elsewhere.
        return ru.ru_maxrss / (1024 * 1024) if sys.platform == "darwin" else ru.ru_maxrss / 1024
    except Exception:
        return 0.0


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
