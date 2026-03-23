"""Natural language search helpers.

Provides:
- Question detection (is this a natural language question?)
- Extractive answer synthesis from ranked chunks
- Key phrase extraction for document previews
"""
from __future__ import annotations

import re
import math
import logging
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

# Question-indicator words at the start of a query
_QUESTION_STARTERS = frozenset({
    "what", "why", "how", "when", "where", "who", "which", "whose", "whom",
    "is", "are", "was", "were", "does", "do", "did", "can", "could",
    "will", "would", "should", "has", "have", "had",
})

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "and", "or", "not", "no", "but", "if", "then", "so", "it", "its",
    "this", "that", "these", "those", "i", "me", "my", "we", "our",
    "you", "your", "he", "she", "they", "their", "what", "why", "how",
    "when", "where", "who", "which",
})


def is_question(query: str) -> bool:
    """Detect whether a query is a natural language question.

    Heuristics:
    - Ends with '?'
    - Starts with a question word
    - Contains 5+ words (long enough to be a question)
    """
    q = query.strip().lower()
    if not q:
        return False

    # Explicit question mark
    if q.endswith("?"):
        return True

    tokens = re.findall(r"\w+", q)
    if not tokens:
        return False

    # Starts with question word AND has enough words
    if tokens[0] in _QUESTION_STARTERS and len(tokens) >= 4:
        return True

    # Contains question words in context of a long query
    if len(tokens) >= 6 and any(t in _QUESTION_STARTERS for t in tokens[:3]):
        return True

    return False


def extract_answer(
    query: str,
    chunks: list[tuple[str, float]],  # (text, score)
    max_sentences: int = 3,
    max_chars: int = 500,
) -> Optional[str]:
    """Synthesize an extractive answer from top-ranked chunks.

    Algorithm:
    1. Split chunks into sentences
    2. Score each sentence by query term overlap (TF-IDF-like)
    3. Return the top sentences, preserving logical order

    Args:
        query: The user's question
        chunks: List of (chunk_text, relevance_score) pairs
        max_sentences: Maximum sentences in the answer
        max_chars: Maximum total characters

    Returns:
        Extracted answer string, or None if no good sentences found.
    """
    if not chunks or not is_question(query):
        return None

    query_tokens = _tokenize(query)
    query_set = set(query_tokens) - _STOP_WORDS
    if not query_set:
        return None

    # Collect candidate sentences from top chunks (weight by chunk score)
    sentences: list[tuple[str, float, int]] = []  # (sentence, score, source_order)
    order = 0
    for chunk_text, chunk_score in chunks[:5]:  # only top 5 chunks
        sents = _split_sentences(chunk_text)
        for sent in sents:
            sent = sent.strip()
            if len(sent) < 20:  # skip very short sentences
                continue
            sent_tokens = _tokenize(sent)
            sent_set = set(sent_tokens) - _STOP_WORDS
            if not sent_set:
                continue

            # Score: query term coverage * chunk relevance * length penalty
            overlap = len(query_set & sent_set)
            if overlap == 0:
                continue

            coverage = overlap / len(query_set)
            precision = overlap / len(sent_set)
            # F1-like measure weighted toward coverage
            f_score = 2 * coverage * precision / (coverage + precision + 1e-9)
            # Boost by chunk relevance score
            final_score = f_score * (0.5 + 0.5 * chunk_score)
            # Length bonus: prefer medium-length sentences (50-150 chars)
            length_bonus = min(1.0, len(sent) / 100) * (1 - max(0, len(sent) - 200) / 500)
            final_score *= (0.7 + 0.3 * length_bonus)

            sentences.append((sent, final_score, order))
            order += 1

    if not sentences:
        return None

    # Pick top N sentences by score, then re-order by original position
    top = sorted(sentences, key=lambda x: x[1], reverse=True)[:max_sentences]
    top = sorted(top, key=lambda x: x[2])  # restore reading order

    answer_parts: list[str] = []
    total_chars = 0
    for sent, score, _ in top:
        if total_chars + len(sent) > max_chars:
            break
        answer_parts.append(sent)
        total_chars += len(sent) + 1

    if not answer_parts:
        return None

    return " ".join(answer_parts)


def extract_key_phrases(
    text: str,
    max_phrases: int = 8,
    min_word_len: int = 4,
) -> list[str]:
    """Extract key phrases from text using term frequency.

    Uses a simple TF-based approach: find frequent multi-word n-grams that
    aren't stopwords. Good enough for document previews without ML.

    Returns a list of key phrases (strings).
    """
    if not text or len(text) < 50:
        return []

    # Extract candidate n-grams (unigrams + bigrams)
    words = [w.lower() for w in re.findall(r"\b[a-zA-Z][a-zA-Z0-9_\-]*\b", text)]
    content_words = [w for w in words if w not in _STOP_WORDS and len(w) >= min_word_len]

    if not content_words:
        return []

    # Unigram counts
    unigram_counts = Counter(content_words)

    # Bigram counts (adjacent content words)
    bigrams: list[str] = []
    prev_idx = -2
    prev_word = ""
    for i, word in enumerate(words):
        if word not in _STOP_WORDS and len(word) >= min_word_len:
            if prev_idx == i - 1 or (i > 0 and words[i-1] in _STOP_WORDS and prev_idx == i - 2):
                # consecutive content words (with at most one stopword between)
                pass
            if prev_idx >= i - 2:
                bigrams.append(f"{prev_word} {word}")
            prev_idx = i
            prev_word = word

    bigram_counts = Counter(bigrams)

    # Combine: prefer bigrams that appear 2+ times, then frequent unigrams
    candidates: list[tuple[str, float]] = []

    for bigram, count in bigram_counts.most_common(20):
        if count >= 2:
            candidates.append((bigram, count * 1.5))  # boost bigrams

    for word, count in unigram_counts.most_common(30):
        if count >= 2:
            candidates.append((word, count))

    # Sort by score, deduplicate (remove unigrams that are part of selected bigrams)
    candidates.sort(key=lambda x: x[1], reverse=True)

    selected: list[str] = []
    used_words: set[str] = set()
    for phrase, score in candidates:
        phrase_words = phrase.split()
        if any(w in used_words for w in phrase_words):
            continue
        selected.append(phrase)
        used_words.update(phrase_words)
        if len(selected) >= max_phrases:
            break

    return selected


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Simple word tokenizer (lowercase alphanumeric)."""
    return re.findall(r"\b[a-zA-Z][a-zA-Z0-9]*\b", text.lower())


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using basic punctuation rules."""
    # Split on sentence-ending punctuation followed by whitespace or end-of-string
    # Keep the punctuation with the sentence
    pattern = r"(?<=[.!?])\s+(?=[A-Z])"
    parts = re.split(pattern, text)

    # Further split on newlines (common in documents)
    sentences: list[str] = []
    for part in parts:
        sub = re.split(r"\n{2,}", part)
        sentences.extend(sub)

    return [s.strip() for s in sentences if s.strip()]
