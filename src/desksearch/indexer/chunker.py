"""Text chunking with paragraph-aware splitting.

Splits text into overlapping chunks of configurable size, preserving
paragraph boundaries where possible. Each chunk includes metadata for
tracing back to the source.
"""
from dataclasses import dataclass

from desksearch.config import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE


@dataclass
class Chunk:
    """A text chunk with source metadata."""

    text: str
    source_file: str
    chunk_index: int
    char_offset: int


def chunk_text(
    text: str,
    source_file: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split text into overlapping chunks, preserving paragraph boundaries.

    Args:
        text: The full text to chunk.
        source_file: Path to the source file (stored in metadata).
        chunk_size: Target chunk size in characters.
        chunk_overlap: Number of overlapping characters between chunks.

    Returns:
        List of Chunk objects with text and metadata.
    """
    if not text or not text.strip():
        return []

    paragraphs = _split_paragraphs(text)
    chunks: list[Chunk] = []
    current_text = ""
    current_offset = 0
    # Track the absolute char offset of where current_text starts
    chunk_start_offset = 0

    for para_offset, para in paragraphs:
        # If adding this paragraph exceeds chunk_size and we have content,
        # finalize the current chunk
        if current_text and len(current_text) + len(para) + 1 > chunk_size:
            chunks.append(Chunk(
                text=current_text.strip(),
                source_file=source_file,
                chunk_index=len(chunks),
                char_offset=chunk_start_offset,
            ))
            # Compute overlap: take the tail of current_text
            overlap_text = current_text[-chunk_overlap:] if chunk_overlap > 0 else ""
            overlap_start = chunk_start_offset + len(current_text) - len(overlap_text)
            current_text = overlap_text
            chunk_start_offset = overlap_start

        if not current_text:
            chunk_start_offset = para_offset

        if current_text:
            current_text += "\n" + para
        else:
            current_text = para

        # Handle paragraphs longer than chunk_size by force-splitting
        while len(current_text) > chunk_size:
            split_at = _find_split_point(current_text, chunk_size)
            chunks.append(Chunk(
                text=current_text[:split_at].strip(),
                source_file=source_file,
                chunk_index=len(chunks),
                char_offset=chunk_start_offset,
            ))
            overlap_text = current_text[split_at - chunk_overlap:split_at] if chunk_overlap > 0 else ""
            current_text = overlap_text + current_text[split_at:]
            chunk_start_offset = chunk_start_offset + split_at - len(overlap_text)

    # Don't forget the last chunk
    if current_text.strip():
        chunks.append(Chunk(
            text=current_text.strip(),
            source_file=source_file,
            chunk_index=len(chunks),
            char_offset=chunk_start_offset,
        ))

    return chunks


def _split_paragraphs(text: str) -> list[tuple[int, str]]:
    """Split text into paragraphs, returning (char_offset, paragraph_text) pairs."""
    paragraphs: list[tuple[int, str]] = []
    current_pos = 0

    for part in text.split("\n\n"):
        stripped = part.strip()
        if stripped:
            # Find actual position in the original text
            paragraphs.append((current_pos, stripped))
        current_pos += len(part) + 2  # +2 for the \n\n separator

    return paragraphs


def _find_split_point(text: str, max_size: int) -> int:
    """Find the best split point near max_size, preferring sentence/word boundaries."""
    if max_size >= len(text):
        return len(text)

    # Try to split at sentence boundary (., !, ?)
    for i in range(max_size, max(max_size - 100, 0), -1):
        if i < len(text) and text[i - 1] in ".!?" and (i >= len(text) or text[i] == " "):
            return i

    # Try to split at word boundary
    for i in range(max_size, max(max_size - 50, 0), -1):
        if i < len(text) and text[i] == " ":
            return i + 1

    # Hard split at max_size
    return max_size
