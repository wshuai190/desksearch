//! XLSX file parser.
//!
//! Extracts text from Excel XLSX files using the calamine crate.

use std::path::Path;
use anyhow::{Context, Result};
use calamine::{open_workbook, Reader, Xlsx};
use tracing::debug;

/// Parse an XLSX file and return its text content.
///
/// Iterates all sheets, formatting each as:
/// `Sheet: <name>\n` followed by tab-separated rows.
pub fn parse_xlsx_file(path: &Path) -> Result<String> {
    let mut workbook: Xlsx<_> = open_workbook(path)
        .with_context(|| format!("Failed to open XLSX file: {}", path.display()))?;

    let sheet_names = workbook.sheet_names().to_vec();
    debug!(path = %path.display(), sheet_count = sheet_names.len(), "Parsing XLSX sheets");

    let mut all_text: Vec<String> = Vec::new();

    for name in &sheet_names {
        if let Ok(range) = workbook.worksheet_range(name) {
            let mut sheet_text = format!("Sheet: {}\n", name);

            for row in range.rows() {
                let cells: Vec<String> = row
                    .iter()
                    .map(|cell| cell.to_string())
                    .collect();
                sheet_text.push_str(&cells.join("\t"));
                sheet_text.push('\n');
            }

            all_text.push(sheet_text);
        }
    }

    Ok(all_text.join("\n"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_missing_file() {
        let result = parse_xlsx_file(Path::new("/nonexistent/file.xlsx"));
        assert!(result.is_err());
    }

    #[test]
    fn test_invalid_xlsx() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("bad.xlsx");
        std::fs::write(&path, b"not a real xlsx").unwrap();
        let result = parse_xlsx_file(&path);
        assert!(result.is_err());
    }
}
