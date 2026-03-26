//! Hybrid search engine combining BM25 and dense retrieval.
//!
//! This is the main search orchestrator. It runs BM25 and dense search
//! in parallel (via rayon), then fuses results using weighted RRF.

use std::path::Path;
use std::time::Instant;

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tracing::{debug, info, warn};

use crate::bm25::BM25Index;
use crate::fusion::{weighted_rrf, RankedItem};
use crate::snippets::{extract_snippet, Snippet};
use crate::vector::VectorIndex;

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
    dense: Option<VectorIndex>,
}

impl SearchEngine {
    /// Create a new search engine with BM25 only (no dense index).
    pub fn new(index_dir: &Path, config: SearchConfig) -> Result<Self> {
        let bm25_dir = index_dir.join("bm25");
        let bm25 = BM25Index::open_or_create(&bm25_dir)
            .with_context(|| "Failed to open BM25 index")?;

        info!("Search engine initialized with {} documents", bm25.num_docs());

        Ok(Self { bm25, config, dense: None })
    }

    /// Create a new hybrid search engine with both BM25 and dense vector index.
    pub fn new_hybrid(index_dir: &Path, config: SearchConfig, vector_index: VectorIndex) -> Result<Self> {
        let bm25_dir = index_dir.join("bm25");
        let bm25 = BM25Index::open_or_create(&bm25_dir)
            .with_context(|| "Failed to open BM25 index")?;

        info!(
            "Hybrid search engine initialized with {} documents, {} vectors",
            bm25.num_docs(),
            vector_index.len()
        );

        Ok(Self { bm25, config, dense: Some(vector_index) })
    }

    /// Execute a hybrid search query.
    ///
    /// When `query_embedding` is provided and a dense index is available,
    /// vector search results are fused with BM25 via RRF.
    pub fn search(&self, query: &SearchQuery, query_embedding: Option<&[f32]>) -> Result<Vec<SearchResult>> {
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

        // Dense search when both embedding and index are available
        let dense_ranked: Vec<RankedItem> = match (&self.dense, query_embedding) {
            (Some(vi), Some(emb)) => {
                let dense_results = vi.search(emb, top_k * 2)?;
                dense_results
                    .into_iter()
                    .map(|(key, distance)| RankedItem {
                        doc_id: key,
                        score: distance,
                    })
                    .collect()
            }
            _ => vec![],
        };

        // Fuse results
        let fused = weighted_rrf(
            &bm25_ranked,
            &dense_ranked,
            self.config.bm25_weight,
            self.config.dense_weight,
            self.config.rrf_k,
            top_k,
        );

        // Build lookup maps from BM25 results
        let bm25_text_map: std::collections::HashMap<u64, &str> = bm25_results
            .iter()
            .map(|r| (r.doc_id, r.text.as_str()))
            .collect();

        let bm25_path_map: std::collections::HashMap<u64, &str> = bm25_results
            .iter()
            .map(|r| (r.doc_id, r.path.as_str()))
            .collect();

        let results: Vec<SearchResult> = fused
            .into_iter()
            .filter_map(|f| {
                let text = bm25_text_map.get(&f.doc_id).copied().unwrap_or("");
                let snippet = extract_snippet(text, &query_terms, self.config.snippet_max_len);
                let file_path = bm25_path_map.get(&f.doc_id).copied().unwrap_or("").to_string();
                let file_name = file_path
                    .rsplit('/')
                    .next()
                    .unwrap_or("")
                    .to_string();

                Some(SearchResult {
                    chunk_id: f.doc_id,
                    file_path,
                    file_name,
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

    /// Whether a dense vector index is available.
    pub fn has_dense(&self) -> bool {
        self.dense.is_some()
    }

    /// Add a vector for a chunk. Errors if no dense index is configured.
    pub fn add_vector(&self, key: u64, vector: &[f32]) -> Result<()> {
        self.dense
            .as_ref()
            .context("no dense index configured")?
            .add(key, vector)
    }

    /// Remove a vector by key. Errors if no dense index is configured.
    pub fn remove_vector(&self, key: u64) -> Result<()> {
        self.dense
            .as_ref()
            .context("no dense index configured")?
            .remove(key)
    }

    /// Save the dense vector index to disk. Errors if no dense index is configured.
    pub fn save_vectors(&self) -> Result<()> {
        self.dense
            .as_ref()
            .context("no dense index configured")?
            .save()
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

        let results = engine.search(&query, None)?;
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

        let results = engine.search(&query, None)?;
        assert!(results.is_empty());

        Ok(())
    }

    #[test]
    fn test_has_dense() -> Result<()> {
        let tmp = TempDir::new()?;

        let engine = SearchEngine::new(tmp.path(), SearchConfig::default())?;
        assert!(!engine.has_dense());

        let vi = VectorIndex::open_or_create(&tmp.path().join("vec.usearch"), 4)?;
        let engine2 = SearchEngine::new_hybrid(tmp.path(), SearchConfig::default(), vi)?;
        assert!(engine2.has_dense());

        Ok(())
    }

    #[test]
    fn test_add_and_remove_vector() -> Result<()> {
        let tmp = TempDir::new()?;
        let vi = VectorIndex::open_or_create(&tmp.path().join("vec.usearch"), 4)?;
        let engine = SearchEngine::new_hybrid(tmp.path(), SearchConfig::default(), vi)?;

        engine.add_vector(1, &[1.0, 0.0, 0.0, 0.0])?;
        engine.add_vector(2, &[0.0, 1.0, 0.0, 0.0])?;
        engine.remove_vector(1)?;

        Ok(())
    }

    #[test]
    fn test_add_vector_without_dense() {
        let tmp = TempDir::new().unwrap();
        let engine = SearchEngine::new(tmp.path(), SearchConfig::default()).unwrap();
        assert!(engine.add_vector(1, &[1.0]).is_err());
    }

    #[test]
    fn test_hybrid_search() -> Result<()> {
        let tmp = TempDir::new()?;
        let vi = VectorIndex::open_or_create(&tmp.path().join("vec.usearch"), 4)?;
        let engine = SearchEngine::new_hybrid(tmp.path(), SearchConfig::default(), vi)?;

        // Index BM25 documents
        let mut writer = engine.bm25().writer(15)?;
        engine.bm25().add_chunk(&mut writer, 1, "Rust programming language", "/doc1.rs")?;
        engine.bm25().add_chunk(&mut writer, 2, "Python data science", "/doc2.py")?;
        engine.bm25().add_chunk(&mut writer, 3, "Search engine design", "/doc3.md")?;
        writer.commit()?;
        engine.bm25.reader.reload()?;

        // Add vectors for same chunk IDs
        engine.add_vector(1, &[1.0, 0.0, 0.0, 0.0])?;
        engine.add_vector(2, &[0.0, 1.0, 0.0, 0.0])?;
        engine.add_vector(3, &[0.0, 0.0, 1.0, 0.0])?;

        let query = SearchQuery {
            text: "rust".to_string(),
            top_k: Some(10),
            file_type: None,
            folder: None,
        };

        // Search with embedding close to doc 1's vector
        let embedding = [0.9, 0.1, 0.0, 0.0];
        let results = engine.search(&query, Some(&embedding))?;
        assert!(!results.is_empty());
        // Doc 1 should be top result — it matches both BM25 ("rust") and dense (close vector)
        assert_eq!(results[0].chunk_id, 1);
        assert!(results[0].bm25_rank.is_some());
        assert!(results[0].dense_rank.is_some());

        Ok(())
    }

    #[test]
    fn test_hybrid_search_without_embedding() -> Result<()> {
        let tmp = TempDir::new()?;
        let vi = VectorIndex::open_or_create(&tmp.path().join("vec.usearch"), 4)?;
        let engine = SearchEngine::new_hybrid(tmp.path(), SearchConfig::default(), vi)?;

        let mut writer = engine.bm25().writer(15)?;
        engine.bm25().add_chunk(&mut writer, 1, "Rust programming", "/doc1.rs")?;
        writer.commit()?;
        engine.bm25.reader.reload()?;

        let query = SearchQuery {
            text: "rust".to_string(),
            top_k: Some(10),
            file_type: None,
            folder: None,
        };

        // Even with dense index, passing None skips vector search
        let results = engine.search(&query, None)?;
        assert!(!results.is_empty());
        assert!(results[0].dense_rank.is_none());

        Ok(())
    }
}
