//! Plain text and code file parser.
//!
//! Reads file content as UTF-8 text, with fallback for binary detection.
//! Handles large files by truncating to a reasonable limit.

use std::path::Path;
use anyhow::{Context, Result};

/// Maximum file size to parse (10MB). Larger files are truncated.
const MAX_FILE_SIZE: u64 = 10 * 1024 * 1024;

/// Parse a plain text or code file.
///
/// Returns the file content as a string. Binary files are detected
/// and rejected. Files larger than 10MB are truncated.
pub fn parse_text_file(path: &Path) -> Result<String> {
    let metadata = std::fs::metadata(path)
        .with_context(|| format!("Failed to read metadata: {}", path.display()))?;

    let file_size = metadata.len();
    if file_size == 0 {
        return Ok(String::new());
    }

    if file_size > MAX_FILE_SIZE {
        // Read only the first MAX_FILE_SIZE bytes
        let bytes = std::fs::read(path)
            .with_context(|| format!("Failed to read file: {}", path.display()))?;
        let truncated = &bytes[..MAX_FILE_SIZE as usize];
        return String::from_utf8(truncated.to_vec())
            .or_else(|_| Ok(String::from_utf8_lossy(truncated).into_owned()));
    }

    let content = std::fs::read_to_string(path).or_else(|_| {
        // Fallback: read as bytes and convert lossy
        let bytes = std::fs::read(path)
            .with_context(|| format!("Failed to read file: {}", path.display()))?;

        // Check if binary (high ratio of null bytes)
        let null_count = bytes.iter().filter(|&&b| b == 0).count();
        if null_count > bytes.len() / 20 {
            anyhow::bail!("File appears to be binary: {}", path.display());
        }

        Ok(String::from_utf8_lossy(&bytes).into_owned())
    })?;

    Ok(content)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_parse_text_file() -> Result<()> {
        let mut f = NamedTempFile::new()?;
        writeln!(f, "Hello, world!")?;
        writeln!(f, "This is a test.")?;

        let content = parse_text_file(f.path())?;
        assert!(content.contains("Hello, world!"));
        assert!(content.contains("This is a test."));
        Ok(())
    }

    #[test]
    fn test_empty_file() -> Result<()> {
        let f = NamedTempFile::new()?;
        let content = parse_text_file(f.path())?;
        assert!(content.is_empty());
        Ok(())
    }
}
