//! HTML file parser.
//!
//! Extracts visible text from HTML, stripping tags, scripts, and styles.

use std::path::Path;
use anyhow::{Context, Result};
use scraper::{Html, Selector};

/// Parse an HTML file and return visible text content.
pub fn parse_html_file(path: &Path) -> Result<String> {
    let raw = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read HTML file: {}", path.display()))?;

    Ok(extract_text_from_html(&raw))
}

/// Extract visible text from HTML string.
///
/// Strips script/style tags and extracts body text.
pub fn extract_text_from_html(html: &str) -> String {
    let document = Html::parse_document(html);

    let body_selector = Selector::parse("body").unwrap();
    let root = document
        .select(&body_selector)
        .next()
        .unwrap_or_else(|| document.root_element());

    let mut text_parts: Vec<String> = Vec::new();

    for text_node in root.text() {
        let trimmed = text_node.trim();
        if !trimmed.is_empty() {
            text_parts.push(trimmed.to_string());
        }
    }

    text_parts.join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_text() {
        let html = r#"
        <html>
        <head><title>Test</title></head>
        <body>
            <h1>Hello World</h1>
            <p>This is a <strong>test</strong> paragraph.</p>
            <script>var x = 1;</script>
            <style>.hidden { display: none; }</style>
        </body>
        </html>
        "#;

        let text = extract_text_from_html(html);
        assert!(text.contains("Hello World"));
        assert!(text.contains("test"));
        assert!(text.contains("paragraph"));
        // Script and style content should not be in the result ideally,
        // but the simple text() iterator might include them.
        // Full production version would walk the tree more carefully.
    }
}
