//! Snippet extraction and highlighting from document chunks.
//!
//! Given a query and a text chunk, extracts the most relevant snippet
//! and highlights matching terms with <mark> tags.

use aho_corasick::AhoCorasick;
use serde::{Deserialize, Serialize};

/// A highlighted snippet from a document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Snippet {
    /// The snippet text with <mark>highlighted</mark> query terms.
    pub text: String,
    /// The plain text without highlighting.
    pub plain: String,
    /// Character offset in the original chunk where this snippet starts.
    pub offset: usize,
}

/// Extract the best snippet from a chunk of text matching the given query terms.
///
/// # Arguments
/// * `text` - The full chunk text.
/// * `query_terms` - Individual query terms to match.
/// * `max_len` - Maximum snippet length in characters (default ~200).
pub fn extract_snippet(text: &str, query_terms: &[&str], max_len: usize) -> Snippet {
    if text.is_empty() || query_terms.is_empty() {
        let truncated = if text.len() > max_len {
            &text[..max_len]
        } else {
            text
        };
        return Snippet {
            text: truncated.to_string(),
            plain: truncated.to_string(),
            offset: 0,
        };
    }

    // Build case-insensitive matcher
    let lower_terms: Vec<String> = query_terms
        .iter()
        .filter(|t| !t.is_empty())
        .map(|t| t.to_lowercase())
        .collect();

    if lower_terms.is_empty() {
        let truncated = if text.len() > max_len {
            &text[..max_len]
        } else {
            text
        };
        return Snippet {
            text: truncated.to_string(),
            plain: truncated.to_string(),
            offset: 0,
        };
    }

    let lower_text = text.to_lowercase();

    // Find all match positions
    let ac = AhoCorasick::builder()
        .ascii_case_insensitive(true)
        .build(&lower_terms)
        .expect("Failed to build AhoCorasick");

    let matches: Vec<usize> = ac
        .find_iter(&lower_text)
        .map(|m| m.start())
        .collect();

    if matches.is_empty() {
        // No matches — return beginning of text
        let truncated = if text.len() > max_len {
            &text[..max_len]
        } else {
            text
        };
        return Snippet {
            text: truncated.to_string(),
            plain: truncated.to_string(),
            offset: 0,
        };
    }

    // Find the window with the most matches
    let best_start = find_best_window(&matches, max_len, text.len());

    // Extract the snippet window
    let end = (best_start + max_len).min(text.len());
    let plain = &text[best_start..end];

    // Highlight matches within the window
    let highlighted = highlight_terms(plain, &lower_terms);

    Snippet {
        text: highlighted,
        plain: plain.to_string(),
        offset: best_start,
    }
}

/// Find the start position of the window containing the most matches.
fn find_best_window(match_positions: &[usize], window_size: usize, text_len: usize) -> usize {
    if match_positions.is_empty() {
        return 0;
    }

    let mut best_start = 0;
    let mut best_count = 0;

    for &pos in match_positions {
        // Try starting the window a bit before this match
        let start = pos.saturating_sub(window_size / 4);
        let end = (start + window_size).min(text_len);

        let count = match_positions
            .iter()
            .filter(|&&p| p >= start && p < end)
            .count();

        if count > best_count {
            best_count = count;
            best_start = start;
        }
    }

    best_start
}

/// Highlight query terms in text with <mark> tags.
fn highlight_terms(text: &str, lower_terms: &[String]) -> String {
    if lower_terms.is_empty() {
        return text.to_string();
    }

    let ac = AhoCorasick::builder()
        .ascii_case_insensitive(true)
        .build(lower_terms)
        .expect("Failed to build AhoCorasick");

    // Collect all match ranges
    let mut ranges: Vec<(usize, usize)> = ac
        .find_iter(text)
        .map(|m| (m.start(), m.end()))
        .collect();

    if ranges.is_empty() {
        return text.to_string();
    }

    // Merge overlapping ranges
    ranges.sort_by_key(|r| r.0);
    let mut merged: Vec<(usize, usize)> = vec![ranges[0]];
    for &(start, end) in &ranges[1..] {
        let last = merged.last_mut().unwrap();
        if start <= last.1 {
            last.1 = last.1.max(end);
        } else {
            merged.push((start, end));
        }
    }

    // Build highlighted string
    let mut result = String::with_capacity(text.len() + merged.len() * 13);
    let mut pos = 0;
    for (start, end) in merged {
        result.push_str(&text[pos..start]);
        result.push_str("<mark>");
        result.push_str(&text[start..end]);
        result.push_str("</mark>");
        pos = end;
    }
    result.push_str(&text[pos..]);

    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_snippet() {
        let text = "Rust is a systems programming language focused on safety and performance.";
        let snippet = extract_snippet(text, &["rust", "safety"], 200);
        assert!(snippet.text.contains("<mark>"));
        assert!(snippet.text.contains("Rust"));
    }

    #[test]
    fn test_highlighting() {
        let result = highlight_terms("Hello World", &["hello".to_string()]);
        assert_eq!(result, "<mark>Hello</mark> World");
    }

    #[test]
    fn test_empty_query() {
        let text = "Some text here";
        let snippet = extract_snippet(text, &[], 200);
        assert_eq!(snippet.plain, text);
    }

    #[test]
    fn test_no_match() {
        let text = "Some text about cats";
        let snippet = extract_snippet(text, &["dogs"], 200);
        assert!(!snippet.text.contains("<mark>"));
    }

    #[test]
    fn test_long_text_window() {
        let text = "A ".repeat(100) + "KEYWORD " + &"B ".repeat(100);
        let snippet = extract_snippet(&text, &["keyword"], 50);
        assert!(snippet.text.contains("<mark>KEYWORD</mark>"));
    }
}
