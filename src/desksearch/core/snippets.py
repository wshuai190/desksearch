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
    context_chars: int = 120,
    highlight_tag: tuple[str, str] = ("<mark>", "</mark>"),
) -> list[Snippet]:
    """Extract snippets using a pre-compiled :class:`QueryMatcher`.

    Prefer this over :func:`extract_snippets` when processing many documents
    for the same query — the pattern is compiled exactly once.
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
    context_chars: int = 120,
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


def _best_windows(
    text: str,
    matches: list[re.Match],
    terms: list[str],
    context_chars: int,
    max_windows: int,
) -> list[tuple[int, int]]:
    """Select the best non-overlapping text windows around matches.

    Scores each window by:
    - Number of unique query terms covered
    - Density of matches (more matches in fewer chars = better)
    """
    text_len = len(text)
    candidates: list[tuple[float, int, int]] = []

    for match in matches:
        center = (match.start() + match.end()) // 2
        start = max(0, center - context_chars)
        end = min(text_len, center + context_chars)

        # Snap to word boundaries
        if start > 0:
            space = text.rfind(" ", start - 30, start)
            if space != -1:
                start = space + 1
        if end < text_len:
            space = text.find(" ", end, end + 30)
            if space != -1:
                end = space

        # Score: unique terms in window + density bonus
        window_text = text[start:end].lower()
        unique_terms = sum(1 for t in terms if t in window_text)
        score = unique_terms + 0.1 * (unique_terms / max(1, end - start) * 100)

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
