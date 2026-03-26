//! DOCX file parser.
//!
//! Extracts text from DOCX (Office Open XML) files by reading
//! word/document.xml from the zip archive and parsing <w:t> elements.

use std::io::Read;
use std::path::Path;
use anyhow::{Context, Result};
use quick_xml::events::Event;
use quick_xml::reader::Reader;
use tracing::debug;

/// Parse a DOCX file and return its text content.
///
/// Extracts text from <w:t> elements in word/document.xml,
/// inserting newlines between paragraphs (<w:p> elements).
pub fn parse_docx_file(path: &Path) -> Result<String> {
    let file = std::fs::File::open(path)
        .with_context(|| format!("Failed to open DOCX file: {}", path.display()))?;

    let mut archive = zip::ZipArchive::new(file)
        .with_context(|| format!("Failed to read DOCX as zip: {}", path.display()))?;

    let mut xml_content = String::new();
    archive
        .by_name("word/document.xml")
        .with_context(|| format!("No word/document.xml in DOCX: {}", path.display()))?
        .read_to_string(&mut xml_content)
        .with_context(|| "Failed to read document.xml")?;

    debug!(path = %path.display(), xml_len = xml_content.len(), "Parsing DOCX document.xml");

    Ok(extract_text_from_docx_xml(&xml_content))
}

/// Extract text from DOCX XML content.
fn extract_text_from_docx_xml(xml: &str) -> String {
    let mut reader = Reader::from_str(xml);
    let mut buf = Vec::new();
    let mut text_parts: Vec<String> = Vec::new();
    let mut current_paragraph = String::new();
    let mut in_text_element = false;

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(ref e)) | Ok(Event::Empty(ref e)) => {
                let local = e.local_name();
                match local.as_ref() {
                    b"p" => {
                        // Start of a new paragraph — flush current
                        if !current_paragraph.is_empty() {
                            text_parts.push(std::mem::take(&mut current_paragraph));
                        }
                    }
                    b"t" => {
                        in_text_element = true;
                    }
                    _ => {}
                }
            }
            Ok(Event::End(ref e)) => {
                if e.local_name().as_ref() == b"t" {
                    in_text_element = false;
                }
            }
            Ok(Event::Text(ref e)) => {
                if in_text_element {
                    if let Ok(text) = e.unescape() {
                        current_paragraph.push_str(&text);
                    }
                }
            }
            Ok(Event::Eof) => break,
            Err(_) => break,
            _ => {}
        }
        buf.clear();
    }

    // Flush last paragraph
    if !current_paragraph.is_empty() {
        text_parts.push(current_paragraph);
    }

    text_parts.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_missing_file() {
        let result = parse_docx_file(Path::new("/nonexistent/file.docx"));
        assert!(result.is_err());
    }

    #[test]
    fn test_invalid_docx() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("bad.docx");
        std::fs::write(&path, b"not a real docx").unwrap();
        let result = parse_docx_file(&path);
        assert!(result.is_err());
    }

    #[test]
    fn test_extract_text_from_xml() {
        let xml = r#"<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:body>
                <w:p><w:r><w:t>Hello World</w:t></w:r></w:p>
                <w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p>
            </w:body>
        </w:document>"#;

        let text = extract_text_from_docx_xml(xml);
        assert!(text.contains("Hello World"));
        assert!(text.contains("Second paragraph"));
        assert!(text.contains('\n'));
    }
}
