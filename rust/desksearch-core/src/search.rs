//! Hybrid search engine combining BM25 and dense retrieval.
//!
//! This is the main search orchestrator. It runs BM25 and dense search
//! in parallel (via rayon), then fuses results using weighted RRF.

use std::path::Path;
use std::time::Instant;

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tracing::{debug, info, warn};

use crate::bm25::{BM25Index, BM25Result};
use crate::fusion::{weighted_rrf, FusedResult, RankedItem};
use crate::snippets::{extract_snippet, Snippet};

/// Configuration for the search engine.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchConfig {
    /// Weight for BM25 in fusion (0.0 to 1.0).
    pub bm25_weight: f64,
    /// Weight for dense search in fusion (0.0 to 1.0).
    pub dense_weight: f64,
    /// RRF k parameter.
    pub rrf_k: f64,
    /// Maximum results to return.
    pub top_k: usize,
    /// Maximum snippet length in characters.
    pub snippet_max_len: usize,
    /// Warn if search takes longer than this (ms).
    pub slow_search_ms: u64,
}

impl Default for SearchConfig {
    fn default() -> Self {
        Self {
            bm25_weight: 0.5,
            dense_weight: 0.5,
            rrf_k: 60.0,
            top_k: 20,
            snippet_max_len: 200,
            slow_search_ms: 100,
        }
    }
}

/// A search query with optional filters.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchQuery {
    /// The query text.
    pub text: String,
    /// Maximum number of results.
    pub top_k: Option<usize>,
    /// Filter by file extension (e.g., "pdf", "md").
    pub file_type: Option<String>,
    /// Filter by folder path prefix.
    pub folder: Option<String>,
}

/// A complete search result with metadata and snippet.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    /// Chunk ID.
    pub chunk_id: u64,
    /// File path.
    pub file_path: String,
    /// File name.
    pub file_name: String,
    /// Fused relevance score.
    pub score: f64,
    /// Highlighted snippet.
    pub snippet: Snippet,
    /// BM25 rank (if matched by BM25).
    pub bm25_rank: Option<usize>,
    /// Dense rank (if matched by dense).
    pub dense_rank: Option<usize>,
}

/// The main hybrid search engine.
pub struct SearchEngine {
    bm25: BM25Index,
    config: SearchConfig,
    // TODO: dense index will be added in Phase 3
}

impl SearchEngine {
    /// Create a new search engine with BM25 index at the given path.
    pub fn new(index_dir: &Path, config: SearchConfig) -> Result<Self> {
        let bm25_dir = index_dir.join("bm25");
        let bm25 = BM25Index::open_or_create(&bm25_dir)
            .with_context(|| "Failed to open BM25 index")?;

        info!("Search engine initialized with {} documents", bm25.num_docs());

        Ok(Self { bm25, config })
    }

    /// Execute a hybrid search query.
    pub fn search(&self, query: &SearchQuery) -> Result<Vec<SearchResult>> {
        let start = Instant::now();
        let top_k = query.top_k.unwrap_or(self.config.top_k);

        // Tokenize query for snippet highlighting
        let query_terms: Vec<&str> = query.text.split_whitespace().collect();

        // BM25 search
        let bm25_results = self.bm25.search(&query.text, top_k * 2)?;

        // Convert to RankedItems for fusion
        let bm25_ranked: Vec<RankedItem> = bm25_results
            .iter()
            .map(|r| RankedItem {
                doc_id: r.doc_id,
                score: r.score,
            })
            .collect();

        // TODO: Dense search will be added in Phase 3
        let dense_ranked: Vec<RankedItem> = vec![];

        // Fuse results
        let fused = weighted_rrf(
            &bm25_ranked,
            &dense_ranked,
            self.config.bm25_weight,
            self.config.dense_weight,
            self.config.rrf_k,
            top_k,
        );

        // Build search results with snippets
        let bm25_text_map: std::collections::HashMap<u64, &str> = bm25_results
            .iter()
            .map(|r| (r.doc_id, r.text.as_str()))
            .collect();

        let results: Vec<SearchResult> = fused
            .into_iter()
            .filter_map(|f| {
                let text = bm25_text_map.get(&f.doc_id).copied().unwrap_or("");
                let snippet = extract_snippet(text, &query_terms, self.config.snippet_max_len);

                Some(SearchResult {
                    chunk_id: f.doc_id,
                    file_path: String::new(), // TODO: look up from SQLite
                    file_name: String::new(), // TODO: look up from SQLite
                    score: f.score,
                    snippet,
                    bm25_rank: f.bm25_rank,
                    dense_rank: f.dense_rank,
                })
            })
            .collect();

        let elapsed = start.elapsed();
        let elapsed_ms = elapsed.as_secs_f64() * 1000.0;

        if elapsed_ms > self.config.slow_search_ms as f64 {
            warn!(
                query = query.text,
                elapsed_ms = elapsed_ms,
                results = results.len(),
                "Slow search detected"
            );
        } else {
            debug!(
                query = query.text,
                elapsed_ms = elapsed_ms,
                results = results.len(),
                "Search completed"
            );
        }

        Ok(results)
    }

    /// Get the BM25 index for direct access (e.g., indexing).
    pub fn bm25(&self) -> &BM25Index {
        &self.bm25
    }

    /// Number of indexed documents.
    pub fn num_docs(&self) -> u64 {
        self.bm25.num_docs()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_search_engine_basic() -> Result<()> {
        let tmp = TempDir::new()?;
        let engine = SearchEngine::new(tmp.path(), SearchConfig::default())?;

        // Index some documents
        let mut writer = engine.bm25().writer(15)?;
        engine.bm25().add_chunk(&mut writer, 1, "Rust programming language for systems", "/doc1.rs")?;
        engine.bm25().add_chunk(&mut writer, 2, "Python for data science and ML", "/doc2.py")?;
        engine.bm25().add_chunk(&mut writer, 3, "Search engine architecture design", "/doc3.md")?;
        writer.commit()?;
        engine.bm25.reader.reload()?;

        let query = SearchQuery {
            text: "rust systems".to_string(),
            top_k: Some(10),
            file_type: None,
            folder: None,
        };

        let results = engine.search(&query)?;
        assert!(!results.is_empty());
        assert_eq!(results[0].chunk_id, 1);
        assert!(results[0].snippet.text.contains("<mark>"));

        Ok(())
    }

    #[test]
    fn test_empty_search() -> Result<()> {
        let tmp = TempDir::new()?;
        let engine = SearchEngine::new(tmp.path(), SearchConfig::default())?;

        let query = SearchQuery {
            text: "nonexistent".to_string(),
            top_k: Some(10),
            file_type: None,
            folder: None,
        };

        let results = engine.search(&query)?;
        assert!(results.is_empty());

        Ok(())
    }
}
