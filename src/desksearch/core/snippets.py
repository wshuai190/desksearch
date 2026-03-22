"""Extract and highlight relevant text snippets from documents."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Snippet:
    """A highlighted excerpt from a document."""
    text: str
    highlighted: str
    start: int
    end: int


def extract_snippets(
    text: str,
    query: str,
    max_snippets: int = 3,
    context_chars: int = 120,
    highlight_tag: tuple[str, str] = ("<mark>", "</mark>"),
) -> list[Snippet]:
    """Extract the most relevant snippets from text given a query.

    Finds passages containing query terms and returns them with highlighting.

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

    # Build a combined regex pattern for all query terms
    escaped = [re.escape(t) for t in terms]
    pattern = re.compile(r"(?:" + "|".join(escaped) + r")", re.IGNORECASE)

    # Find all match positions
    matches = list(pattern.finditer(text))
    if not matches:
        return []

    # Score windows by term coverage and density
    windows = _best_windows(text, matches, terms, context_chars, max_snippets)

    open_tag, close_tag = highlight_tag
    snippets: list[Snippet] = []

    for start, end in windows:
        raw = text[start:end]
        highlighted = pattern.sub(
            lambda m: f"{open_tag}{m.group()}{close_tag}", raw
        )

        # Add ellipsis for truncated boundaries
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""

        snippets.append(Snippet(
            text=f"{prefix}{raw}{suffix}",
            highlighted=f"{prefix}{highlighted}{suffix}",
            start=start,
            end=end,
        ))

    return snippets


def _tokenize_query(query: str) -> list[str]:
    """Split query into searchable terms, removing stop words and short tokens."""
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
