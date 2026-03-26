//! Document parsers for various file formats.
//!
//! Each parser takes a file path and returns extracted plain text.
//! The parser registry maps file extensions to parser functions.

pub mod text;
pub mod html;
pub mod pdf;
pub mod docx;
pub mod pptx;
pub mod xlsx;

use std::path::Path;
use anyhow::Result;
use tracing::debug;

/// Parse a file and return its text content.
///
/// Automatically selects the appropriate parser based on file extension.
/// Returns None if the file format is not supported.
pub fn parse_file(path: &Path) -> Result<Option<String>> {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    let result = match ext.as_str() {
        // Plain text formats
        "txt" | "md" | "markdown" | "rst" | "org" | "csv" | "tsv" | "log" | "json" | "yaml"
        | "yml" | "toml" | "xml" | "ini" | "cfg" | "conf" => {
            Some(text::parse_text_file(path)?)
        }
        // Code files
        "py" | "js" | "ts" | "jsx" | "tsx" | "rs" | "go" | "java" | "c" | "cpp" | "h"
        | "hpp" | "cs" | "rb" | "php" | "swift" | "kt" | "scala" | "lua" | "sh" | "bash"
        | "zsh" | "sql" | "r" | "m" | "mm" => {
            Some(text::parse_text_file(path)?)
        }
        // HTML
        "html" | "htm" => Some(html::parse_html_file(path)?),
        // PDF
        "pdf" => Some(pdf::parse_pdf_file(path)?),
        // Office documents
        "docx" => Some(docx::parse_docx_file(path)?),
        "pptx" => Some(pptx::parse_pptx_file(path)?),
        "xlsx" => Some(xlsx::parse_xlsx_file(path)?),
        _ => {
            debug!(ext = ext, path = %path.display(), "Unsupported file format");
            None
        }
    };

    Ok(result)
}

/// Check if a file extension is supported for parsing.
pub fn is_supported(path: &Path) -> bool {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    matches!(
        ext.as_str(),
        "txt" | "md" | "markdown" | "rst" | "org" | "csv" | "tsv" | "log"
            | "json" | "yaml" | "yml" | "toml" | "xml" | "ini" | "cfg" | "conf"
            | "py" | "js" | "ts" | "jsx" | "tsx" | "rs" | "go" | "java"
            | "c" | "cpp" | "h" | "hpp" | "cs" | "rb" | "php" | "swift"
            | "kt" | "scala" | "lua" | "sh" | "bash" | "zsh" | "sql" | "r"
            | "m" | "mm"
            | "html" | "htm"
            | "pdf" | "docx" | "pptx" | "xlsx"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_supported() {
        assert!(is_supported(Path::new("test.txt")));
        assert!(is_supported(Path::new("test.py")));
        assert!(is_supported(Path::new("test.rs")));
        assert!(is_supported(Path::new("test.html")));
        assert!(!is_supported(Path::new("test.exe")));
        assert!(!is_supported(Path::new("test.png")));
        assert!(is_supported(Path::new("report.pdf")));
        assert!(is_supported(Path::new("doc.docx")));
        assert!(is_supported(Path::new("slides.pptx")));
        assert!(is_supported(Path::new("data.xlsx")));
    }
}
