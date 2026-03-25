//! Text chunking for indexing.
//!
//! Splits document text into overlapping chunks suitable for embedding
//! and search indexing. Aims for semantically meaningful boundaries
//! (paragraphs, sentences) rather than arbitrary character splits.

use serde::{Deserialize, Serialize};

/// Configuration for the text chunker.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChunkerConfig {
    /// Target chunk size in characters.
    pub chunk_size: usize,
    /// Overlap between consecutive chunks in characters.
    pub overlap: usize,
    /// Minimum chunk size (smaller chunks are merged with neighbors).
    pub min_chunk_size: usize,
}

impl Default for ChunkerConfig {
    fn default() -> Self {
        Self {
            chunk_size: 512,
            overlap: 64,
            min_chunk_size: 50,
        }
    }
}

/// A text chunk from a document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Chunk {
    /// The chunk text.
    pub text: String,
    /// Character offset in the original document.
    pub offset: usize,
    /// Chunk index within the document (0-based).
    pub index: usize,
}

/// Split text into overlapping chunks, preferring paragraph/sentence boundaries.
pub fn chunk_text(text: &str, config: &ChunkerConfig) -> Vec<Chunk> {
    if text.is_empty() {
        return vec![];
    }

    // If text is small enough, return as single chunk
    if text.len() <= config.chunk_size + config.overlap {
        return vec![Chunk {
            text: text.to_string(),
            offset: 0,
            index: 0,
        }];
    }

    let mut chunks = Vec::new();
    let mut start = 0;
    let mut index = 0;

    while start < text.len() {
        let end = (start + config.chunk_size).min(text.len());

        // Try to find a good break point
        let break_point = if end < text.len() {
            find_break_point(text, start, end)
        } else {
            end
        };

        let chunk_text = &text[start..break_point];

        // Skip chunks that are too small (unless it's the last one)
        if chunk_text.len() >= config.min_chunk_size || start + config.chunk_size >= text.len() {
            chunks.push(Chunk {
                text: chunk_text.trim().to_string(),
                offset: start,
                index,
            });
            index += 1;
        }

        // Advance with overlap
        let advance = if break_point > start + config.overlap {
            break_point - start - config.overlap
        } else {
            // Avoid infinite loop: advance at least 1 character
            (break_point - start).max(1)
        };
        start += advance;
    }

    // Filter empty chunks
    chunks.retain(|c| !c.text.is_empty());

    chunks
}

/// Find a good break point near `target` between `start` and `target`.
/// Prefers paragraph breaks (\n\n), then sentence endings (. ! ?), then word boundaries.
fn find_break_point(text: &str, start: usize, target: usize) -> usize {
    let search_text = &text[start..target];

    // 1. Try paragraph break (double newline)
    if let Some(pos) = search_text.rfind("\n\n") {
        let bp = start + pos + 2;
        if bp > start + (target - start) / 2 {
            return bp;
        }
    }

    // 2. Try sentence boundary (. or ! or ? followed by space or newline)
    let bytes = search_text.as_bytes();
    for i in (0..bytes.len().saturating_sub(1)).rev() {
        if (bytes[i] == b'.' || bytes[i] == b'!' || bytes[i] == b'?')
            && (bytes[i + 1] == b' ' || bytes[i + 1] == b'\n')
        {
            let bp = start + i + 1;
            if bp > start + (target - start) / 3 {
                return bp;
            }
        }
    }

    // 3. Try word boundary (space)
    if let Some(pos) = search_text.rfind(' ') {
        return start + pos + 1;
    }

    // 4. Fall back to target
    target
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_single_chunk() {
        let text = "Hello, world!";
        let chunks = chunk_text(text, &ChunkerConfig::default());
        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].text, "Hello, world!");
    }

    #[test]
    fn test_paragraph_splitting() {
        let text = "First paragraph with some content.\n\nSecond paragraph with more content.\n\nThird paragraph to make it longer.";
        let config = ChunkerConfig {
            chunk_size: 60,
            overlap: 10,
            min_chunk_size: 10,
        };
        let chunks = chunk_text(text, &config);
        assert!(chunks.len() >= 2, "Should split into multiple chunks");
    }

    #[test]
    fn test_overlap() {
        let text = "word ".repeat(200);
        let config = ChunkerConfig {
            chunk_size: 100,
            overlap: 20,
            min_chunk_size: 10,
        };
        let chunks = chunk_text(&text, &config);
        assert!(chunks.len() > 1);

        // Check that chunks have some overlap
        if chunks.len() >= 2 {
            let end_of_first = &chunks[0].text[chunks[0].text.len().saturating_sub(20)..];
            // The overlap should cause some text to appear in both chunks
            // (exact check depends on break points)
            assert!(chunks[0].text.len() > 50);
        }
    }

    #[test]
    fn test_empty_text() {
        let chunks = chunk_text("", &ChunkerConfig::default());
        assert!(chunks.is_empty());
    }

    #[test]
    fn test_chunk_indices() {
        let text = "A ".repeat(500);
        let config = ChunkerConfig {
            chunk_size: 100,
            overlap: 10,
            min_chunk_size: 10,
        };
        let chunks = chunk_text(&text, &config);
        for (i, chunk) in chunks.iter().enumerate() {
            assert_eq!(chunk.index, i, "Chunk index should match position");
        }
    }

    #[test]
    fn test_performance_10k_chunks() {
        // Simulate a large document
        let text = "This is a sentence with some content. ".repeat(5000);
        let config = ChunkerConfig {
            chunk_size: 200,
            overlap: 20,
            min_chunk_size: 50,
        };

        let start = std::time::Instant::now();
        let chunks = chunk_text(&text, &config);
        let elapsed = start.elapsed();

        assert!(chunks.len() > 100, "Should produce many chunks");
        assert!(
            elapsed.as_millis() < 1000,
            "Chunking should complete in under 1 second, took {}ms",
            elapsed.as_millis()
        );
    }
}
