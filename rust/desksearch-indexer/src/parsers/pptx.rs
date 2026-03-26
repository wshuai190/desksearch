//! PPTX file parser.
//!
//! Extracts text from PowerPoint PPTX files by reading slide XML files
//! from the zip archive and parsing <a:t> text elements.

use std::io::Read;
use std::path::Path;
use anyhow::{Context, Result};
use quick_xml::events::Event;
use quick_xml::reader::Reader;
use tracing::debug;

/// Parse a PPTX file and return its text content.
///
/// Iterates over all slides (ppt/slides/slide*.xml) and extracts
/// text from <a:t> elements, separating slides with dividers.
pub fn parse_pptx_file(path: &Path) -> Result<String> {
    let file = std::fs::File::open(path)
        .with_context(|| format!("Failed to open PPTX file: {}", path.display()))?;

    let mut archive = zip::ZipArchive::new(file)
        .with_context(|| format!("Failed to read PPTX as zip: {}", path.display()))?;

    // Collect slide file names and sort them
    let mut slide_names: Vec<String> = (0..archive.len())
        .filter_map(|i| {
            let name = archive.by_index(i).ok()?.name().to_string();
            if name.starts_with("ppt/slides/slide") && name.ends_with(".xml") {
                Some(name)
            } else {
                None
            }
        })
        .collect();
    slide_names.sort();

    debug!(path = %path.display(), slide_count = slide_names.len(), "Parsing PPTX slides");

    let mut all_text: Vec<String> = Vec::new();

    for (i, slide_name) in slide_names.iter().enumerate() {
        let mut xml_content = String::new();
        archive
            .by_name(slide_name)
            .with_context(|| format!("Failed to read slide: {}", slide_name))?
            .read_to_string(&mut xml_content)
            .with_context(|| format!("Failed to read slide content: {}", slide_name))?;

        let slide_text = extract_text_from_slide_xml(&xml_content);
        if !slide_text.is_empty() {
            all_text.push(format!("--- Slide {} ---\n{}", i + 1, slide_text));
        }
    }

    Ok(all_text.join("\n\n"))
}

/// Extract text from a PPTX slide XML.
fn extract_text_from_slide_xml(xml: &str) -> String {
    let mut reader = Reader::from_str(xml);
    let mut buf = Vec::new();
    let mut text_parts: Vec<String> = Vec::new();
    let mut in_text_element = false;

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(ref e)) => {
                if e.local_name().as_ref() == b"t" {
                    in_text_element = true;
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
                        let trimmed = text.trim();
                        if !trimmed.is_empty() {
                            text_parts.push(trimmed.to_string());
                        }
                    }
                }
            }
            Ok(Event::Eof) => break,
            Err(_) => break,
            _ => {}
        }
        buf.clear();
    }

    text_parts.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_missing_file() {
        let result = parse_pptx_file(Path::new("/nonexistent/file.pptx"));
        assert!(result.is_err());
    }

    #[test]
    fn test_invalid_pptx() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("bad.pptx");
        std::fs::write(&path, b"not a real pptx").unwrap();
        let result = parse_pptx_file(&path);
        assert!(result.is_err());
    }

    #[test]
    fn test_extract_slide_text() {
        let xml = r#"<?xml version="1.0" encoding="UTF-8"?>
        <p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
               xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
            <p:cSld>
                <p:spTree>
                    <p:sp>
                        <p:txBody>
                            <a:p><a:r><a:t>Slide Title</a:t></a:r></a:p>
                            <a:p><a:r><a:t>Bullet point</a:t></a:r></a:p>
                        </p:txBody>
                    </p:sp>
                </p:spTree>
            </p:cSld>
        </p:sld>"#;

        let text = extract_text_from_slide_xml(xml);
        assert!(text.contains("Slide Title"));
        assert!(text.contains("Bullet point"));
    }
}
