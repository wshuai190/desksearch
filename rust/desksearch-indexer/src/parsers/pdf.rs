//! PDF file parser.
//!
//! Extracts text content from PDF files using pdf-extract.

use std::path::Path;
use anyhow::{Context, Result};
use tracing::warn;

/// Parse a PDF file and return its text content.
///
/// Extracts text from each page and concatenates with newlines.
/// Returns an error for encrypted or malformed PDFs.
pub fn parse_pdf_file(path: &Path) -> Result<String> {
    let bytes = std::fs::read(path)
        .with_context(|| format!("Failed to read PDF file: {}", path.display()))?;

    let text = pdf_extract::extract_text_from_mem(&bytes).map_err(|e| {
        warn!(path = %path.display(), error = %e, "Failed to extract text from PDF");
        anyhow::anyhow!("Failed to parse PDF {}: {}", path.display(), e)
    })?;

    Ok(text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_missing_file() {
        let result = parse_pdf_file(Path::new("/nonexistent/file.pdf"));
        assert!(result.is_err());
    }

    #[test]
    fn test_invalid_pdf() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("bad.pdf");
        std::fs::write(&path, b"not a real pdf").unwrap();
        let result = parse_pdf_file(&path);
        assert!(result.is_err());
    }
}
