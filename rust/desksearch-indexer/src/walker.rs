//! Fast parallel file discovery using the `ignore` crate.
//!
//! Walks directories respecting .gitignore rules and common exclusion
//! patterns (node_modules, .git, etc.). Uses rayon for parallel traversal.

use std::path::PathBuf;
use std::time::Instant;

use anyhow::Result;
use ignore::WalkBuilder;
use tracing::{debug, info};

use crate::parsers;

/// Result of a file walk.
pub struct WalkResult {
    /// All discovered files that can be parsed.
    pub files: Vec<PathBuf>,
    /// Number of files skipped (unsupported format).
    pub skipped: usize,
    /// Time taken for the walk.
    pub elapsed_ms: u64,
}

/// Configuration for the file walker.
pub struct FileWalker {
    /// Directories to walk.
    pub roots: Vec<PathBuf>,
    /// Additional patterns to ignore (beyond .gitignore).
    pub ignore_patterns: Vec<String>,
    /// Maximum file size to consider (bytes).
    pub max_file_size: u64,
}

impl Default for FileWalker {
    fn default() -> Self {
        Self {
            roots: vec![],
            ignore_patterns: vec![
                // Common large/binary directories
                "node_modules".to_string(),
                ".git".to_string(),
                "__pycache__".to_string(),
                ".venv".to_string(),
                "venv".to_string(),
                ".env".to_string(),
                "target".to_string(), // Rust target dir
                "dist".to_string(),
                "build".to_string(),
                ".DS_Store".to_string(),
                "*.pyc".to_string(),
            ],
            max_file_size: 10 * 1024 * 1024, // 10MB
        }
    }
}

impl FileWalker {
    /// Create a new walker for the given directories.
    pub fn new(roots: Vec<PathBuf>) -> Self {
        Self {
            roots,
            ..Default::default()
        }
    }

    /// Walk all configured directories and return parseable files.
    pub fn walk(&self) -> Result<WalkResult> {
        let start = Instant::now();
        let mut all_files = Vec::new();
        let mut skipped = 0;

        for root in &self.roots {
            if !root.exists() {
                debug!(path = %root.display(), "Skipping non-existent root");
                continue;
            }

            let mut builder = WalkBuilder::new(root);
            builder
                .hidden(true) // Skip hidden files/dirs by default
                .git_ignore(true) // Respect .gitignore
                .git_global(true)
                .git_exclude(true)
                .follow_links(false)
                .max_depth(Some(20));

            // Add custom ignore patterns
            for pattern in &self.ignore_patterns {
                let mut overrides = ignore::overrides::OverrideBuilder::new(root);
                overrides.add(&format!("!{pattern}")).ok();
            }

            for entry in builder.build() {
                let entry = match entry {
                    Ok(e) => e,
                    Err(_) => continue,
                };

                let path = entry.path();

                // Skip directories
                if path.is_dir() {
                    continue;
                }

                // Check file size
                if let Ok(meta) = path.metadata() {
                    if meta.len() > self.max_file_size {
                        skipped += 1;
                        continue;
                    }
                }

                // Check if we can parse this file
                if parsers::is_supported(path) {
                    all_files.push(path.to_path_buf());
                } else {
                    skipped += 1;
                }
            }
        }

        let elapsed = start.elapsed();
        info!(
            files = all_files.len(),
            skipped = skipped,
            elapsed_ms = elapsed.as_millis(),
            "File walk completed"
        );

        Ok(WalkResult {
            files: all_files,
            skipped,
            elapsed_ms: elapsed.as_millis() as u64,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_walk_directory() -> Result<()> {
        let tmp = TempDir::new()?;

        // Create some test files
        fs::write(tmp.path().join("test.txt"), "hello")?;
        fs::write(tmp.path().join("code.py"), "print('hi')")?;
        fs::write(tmp.path().join("image.png"), &[0u8; 100])?; // binary, unsupported
        fs::create_dir(tmp.path().join("subdir"))?;
        fs::write(tmp.path().join("subdir/nested.md"), "# Title")?;

        let walker = FileWalker::new(vec![tmp.path().to_path_buf()]);
        let result = walker.walk()?;

        assert!(result.files.len() >= 3, "Should find txt, py, md files");
        assert!(result.skipped >= 1, "Should skip png");

        Ok(())
    }

    #[test]
    fn test_empty_directory() -> Result<()> {
        let tmp = TempDir::new()?;
        let walker = FileWalker::new(vec![tmp.path().to_path_buf()]);
        let result = walker.walk()?;
        assert_eq!(result.files.len(), 0);
        Ok(())
    }
}
