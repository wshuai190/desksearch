//! Reciprocal Rank Fusion (RRF) for combining BM25 and dense results.
//!
//! Implements weighted RRF as described in:
//! Cormack, Clarke, Buettcher (2009) — Reciprocal Rank Fusion
//! outperforms Condorcet and individual Rank Learning Methods.

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

/// A fused search result combining scores from multiple retrieval methods.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FusedResult {
    /// The document/chunk ID.
    pub doc_id: u64,
    /// Combined RRF score.
    pub score: f64,
    /// BM25 score (if available).
    pub bm25_score: Option<f32>,
    /// Dense similarity score (if available).
    pub dense_score: Option<f32>,
    /// Original rank in BM25 results (1-indexed).
    pub bm25_rank: Option<usize>,
    /// Original rank in dense results (1-indexed).
    pub dense_rank: Option<usize>,
}

/// A scored item from a single retrieval method.
#[derive(Debug, Clone)]
pub struct RankedItem {
    pub doc_id: u64,
    pub score: f32,
}

/// Fuse two ranked lists using weighted Reciprocal Rank Fusion.
///
/// # Arguments
/// * `bm25_results` - Results from BM25 search, ordered by relevance.
/// * `dense_results` - Results from dense/vector search, ordered by relevance.
/// * `bm25_weight` - Weight for BM25 component (default 0.5).
/// * `dense_weight` - Weight for dense component (default 0.5).
/// * `k` - RRF parameter (default 60, standard value from the paper).
/// * `top_n` - Maximum number of results to return.
pub fn weighted_rrf(
    bm25_results: &[RankedItem],
    dense_results: &[RankedItem],
    bm25_weight: f64,
    dense_weight: f64,
    k: f64,
    top_n: usize,
) -> Vec<FusedResult> {
    let mut scores: HashMap<u64, FusedResult> = HashMap::new();

    // Process BM25 results
    for (rank, item) in bm25_results.iter().enumerate() {
        let rrf_score = bm25_weight / (k + (rank + 1) as f64);
        let entry = scores.entry(item.doc_id).or_insert(FusedResult {
            doc_id: item.doc_id,
            score: 0.0,
            bm25_score: None,
            dense_score: None,
            bm25_rank: None,
            dense_rank: None,
        });
        entry.score += rrf_score;
        entry.bm25_score = Some(item.score);
        entry.bm25_rank = Some(rank + 1);
    }

    // Process dense results
    for (rank, item) in dense_results.iter().enumerate() {
        let rrf_score = dense_weight / (k + (rank + 1) as f64);
        let entry = scores.entry(item.doc_id).or_insert(FusedResult {
            doc_id: item.doc_id,
            score: 0.0,
            bm25_score: None,
            dense_score: None,
            bm25_rank: None,
            dense_rank: None,
        });
        entry.score += rrf_score;
        entry.dense_score = Some(item.score);
        entry.dense_rank = Some(rank + 1);
    }

    // Sort by fused score descending
    let mut results: Vec<FusedResult> = scores.into_values().collect();
    results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
    results.truncate(top_n);

    results
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rrf_basic() {
        let bm25 = vec![
            RankedItem { doc_id: 1, score: 10.0 },
            RankedItem { doc_id: 2, score: 8.0 },
            RankedItem { doc_id: 3, score: 5.0 },
        ];
        let dense = vec![
            RankedItem { doc_id: 2, score: 0.95 },
            RankedItem { doc_id: 4, score: 0.90 },
            RankedItem { doc_id: 1, score: 0.85 },
        ];

        let results = weighted_rrf(&bm25, &dense, 0.5, 0.5, 60.0, 10);

        // Doc 2 should be top: rank 2 in BM25 + rank 1 in dense
        assert!(!results.is_empty());
        // Both doc 1 and doc 2 should be in results with high scores
        let doc_ids: Vec<u64> = results.iter().map(|r| r.doc_id).collect();
        assert!(doc_ids.contains(&1));
        assert!(doc_ids.contains(&2));
    }

    #[test]
    fn test_rrf_single_source() {
        let bm25 = vec![
            RankedItem { doc_id: 1, score: 10.0 },
        ];
        let dense: Vec<RankedItem> = vec![];

        let results = weighted_rrf(&bm25, &dense, 0.5, 0.5, 60.0, 10);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].doc_id, 1);
        assert!(results[0].bm25_score.is_some());
        assert!(results[0].dense_score.is_none());
    }

    #[test]
    fn test_rrf_top_n() {
        let bm25: Vec<RankedItem> = (1..=100)
            .map(|i| RankedItem { doc_id: i, score: (100 - i) as f32 })
            .collect();
        let dense = vec![];

        let results = weighted_rrf(&bm25, &dense, 1.0, 0.0, 60.0, 10);
        assert_eq!(results.len(), 10);
    }
}
