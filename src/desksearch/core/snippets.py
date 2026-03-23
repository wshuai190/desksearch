"""Extract and highlight relevant text snippets from documents."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import NamedTuple


@dataclass(frozen=True)
class Snippet:
    """A highlighted excerpt from a document."""
    text: str
    highlighted: str
    start: int
    end: int


class QueryMatcher(NamedTuple):
    """Pre-compiled query matcher — compile once, apply to many documents.

    Use :func:`make_query_matcher` to create one, then pass it to
    :func:`extract_snippets_with_pattern` for every result document.
    """
    pattern: re.Pattern
    terms: list[str]


# Sentence-boundary pattern for snapping windows to sentence starts/ends.
_SENT_END_RE = re.compile(r'[.!?]+[\s]+')


def make_query_pattern(query: str) -> QueryMatcher | None:
    """Compile a combined regex + term list for all terms in *query*.

    Returns ``None`` if the query yields no searchable terms.
    The compiled pattern is cached (LRU, 512 entries) so identical queries
    never recompile. Use the returned :class:`QueryMatcher` with
    :func:`extract_snippets_with_pattern`.
    """
    terms = _tokenize_query(query)
    if not terms:
        return None
    terms_key = tuple(sorted(terms))
    pattern = _compile_pattern(terms_key)
    return QueryMatcher(pattern=pattern, terms=list(terms_key))


@lru_cache(maxsize=512)
def _compile_pattern(terms_key: tuple[str, ...]) -> re.Pattern:
    """Return a compiled regex matching any of the given terms (case-insensitive).

    Cached by the sorted-tuple of terms so query variations with the same
    vocabulary (e.g. "python ML" vs "ML python") share one compiled entry.
    """
    escaped = [re.escape(t) for t in terms_key]
    return re.compile(r"(?:" + "|".join(escaped) + r")", re.IGNORECASE)


def extract_snippets_with_pattern(
    text: str,
    matcher: QueryMatcher | None,
    max_snippets: int = 3,
    context_chars: int = 150,
    highlight_tag: tuple[str, str] = ("<mark>", "</mark>"),
) -> list[Snippet]:
    """Extract snippets using a pre-compiled :class:`QueryMatcher`.

    Prefer this over :func:`extract_snippets` when processing many documents
    for the same query — the pattern is compiled exactly once.

    The returned snippets show the *most relevant* part of the text (highest
    term density and unique-term coverage), not just the beginning.
    """
    if not text or matcher is None:
        return []

    matches = list(matcher.pattern.finditer(text))
    if not matches:
        return []

    windows = _best_windows(text, matches, matcher.terms, context_chars, max_snippets)
    return _windows_to_snippets(text, windows, matcher.pattern, highlight_tag)


def extract_snippets(
    text: str,
    query: str,
    max_snippets: int = 3,
    context_chars: int = 150,
    highlight_tag: tuple[str, str] = ("<mark>", "</mark>"),
) -> list[Snippet]:
    """Extract the most relevant snippets from text given a query.

    Finds passages containing query terms and returns them with highlighting.
    Use :func:`make_query_pattern` + :func:`extract_snippets_with_pattern`
    when processing many documents for the same query (avoids repeated
    pattern compilation).

    Args:
        text: Full document text.
        query: User search query.
        max_snippets: Maximum number of snippets to return.
        context_chars: Characters of context around each match.
        highlight_tag: Opening and closing tags for highlighting.

    Returns:
        List of Snippet objects, best matches first.
    """
    if not text or not query.strip():
        return []

    terms = _tokenize_query(query)
    if not terms:
        return []

    pattern = _compile_pattern(tuple(sorted(terms)))
    matches = list(pattern.finditer(text))
    if not matches:
        return []

    windows = _best_windows(text, matches, terms, context_chars, max_snippets)
    return _windows_to_snippets(text, windows, pattern, highlight_tag)


def _windows_to_snippets(
    text: str,
    windows: list[tuple[int, int]],
    pattern: re.Pattern,
    highlight_tag: tuple[str, str],
) -> list[Snippet]:
    """Convert (start, end) windows into Snippet objects with highlighting."""
    open_tag, close_tag = highlight_tag
    snippets: list[Snippet] = []
    text_len = len(text)

    for start, end in windows:
        raw = text[start:end]
        highlighted = pattern.sub(
            lambda m: f"{open_tag}{m.group()}{close_tag}", raw
        )
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < text_len else ""
        snippets.append(Snippet(
            text=f"{prefix}{raw}{suffix}",
            highlighted=f"{prefix}{highlighted}{suffix}",
            start=start,
            end=end,
        ))

    return snippets


@lru_cache(maxsize=1024)
def _tokenize_query(query: str) -> list[str]:
    """Split query into searchable terms, removing stop words and short tokens.

    Cached so the same query string isn't tokenized more than once.
    """
    stop_words = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "in", "on", "at", "to", "for", "of", "with", "by", "from", "and",
        "or", "not", "no", "but", "if", "then", "so", "as", "it", "its",
        "this", "that", "these", "those", "i", "me", "my", "we", "our",
        "you", "your", "he", "she", "they", "them", "his", "her", "do",
        "does", "did", "has", "have", "had", "will", "would", "can", "could",
    }
    tokens = re.findall(r"\w+", query.lower())
    return [t for t in tokens if t not in stop_words and len(t) > 1]


def _snap_to_sentence_boundary(text: str, start: int, end: int) -> tuple[int, int]:
    """Expand/contract (start, end) to align with sentence boundaries.

    * Start is moved *back* to the beginning of the sentence that contains it.
    * End is moved *forward* to the end of the sentence that contains it.

    This avoids mid-sentence cuts in the displayed snippet.
    """
    text_len = len(text)

    # --- Snap start backward to the sentence start ---
    # Look for the most recent sentence-ending punctuation before `start`.
    look_back = max(0, start - 200)
    prefix = text[look_back:start]
    # Find the last sentence-end marker in the look-back region.
    last_end = None
    for m in _SENT_END_RE.finditer(prefix):
        last_end = m
    if last_end is not None:
        new_start = look_back + last_end.end()
    else:
        # Fall back to the nearest word boundary
        space = text.rfind(" ", look_back, start)
        new_start = (space + 1) if space != -1 else start

    # --- Snap end forward to the sentence end ---
    look_ahead = min(text_len, end + 200)
    suffix = text[end:look_ahead]
    m_end = _SENT_END_RE.search(suffix)
    if m_end:
        new_end = end + m_end.start() + 1  # include the punctuation
    else:
        # Fall back to word boundary
        space = text.find(" ", end, end + 50)
        new_end = space if space != -1 else end

    # Clamp
    new_start = max(0, min(new_start, start))
    new_end = min(text_len, max(new_end, end))
    return new_start, new_end


def _best_windows(
    text: str,
    matches: list[re.Match],
    terms: list[str],
    context_chars: int,
    max_windows: int,
) -> list[tuple[int, int]]:
    """Select the best non-overlapping text windows around matches.

    Windows are scored by:
    1. Unique query terms covered (primary — strongly preferred)
    2. Match density (secondary — more hits in fewer chars)

    Windows are snapped to sentence boundaries for cleaner display.
    """
    text_len = len(text)
    candidates: list[tuple[float, int, int]] = []

    # Group nearby matches into clusters for better window selection
    clusters: list[list[re.Match]] = []
    if matches:
        current_cluster = [matches[0]]
        for m in matches[1:]:
            if m.start() - current_cluster[-1].end() <= context_chars * 2:
                current_cluster.append(m)
            else:
                clusters.append(current_cluster)
                current_cluster = [m]
        clusters.append(current_cluster)

    for cluster in clusters:
        # Centre the window on the midpoint of the cluster
        cluster_start = cluster[0].start()
        cluster_end = cluster[-1].end()
        center = (cluster_start + cluster_end) // 2

        start = max(0, center - context_chars)
        end = min(text_len, center + context_chars)

        # Snap to sentence boundaries
        start, end = _snap_to_sentence_boundary(text, start, end)

        # Score: strongly reward unique terms, then add density bonus
        window_text = text[start:end].lower()
        n_unique = sum(1 for t in terms if t in window_text)
        n_matches = len([m for m in cluster if start <= m.start() < end])
        window_len = max(1, end - start)
        density = n_matches / (window_len / 100)

        # Primary weight: unique terms count (×10) + density bonus
        score = n_unique * 10.0 + density

        candidates.append((score, start, end))

    # Sort by score descending
    candidates.sort(key=lambda c: c[0], reverse=True)

    # Pick non-overlapping windows
    selected: list[tuple[int, int]] = []
    for _score, start, end in candidates:
        if len(selected) >= max_windows:
            break
        if any(s < end and start < e for s, e in selected):
            continue
        selected.append((start, end))

    # Return in document order
    selected.sort()
    return selected
