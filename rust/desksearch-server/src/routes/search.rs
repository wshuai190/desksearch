//! Search endpoint: POST /api/search

use std::sync::Arc;

use axum::{
    extract::State,
    routing::post,
    Json, Router,
};
use serde::{Deserialize, Serialize};
use tracing::warn;

use crate::state::AppState;
use desksearch_core::SearchQuery;

#[derive(Debug, Deserialize)]
pub struct SearchRequest {
    pub query: String,
    #[serde(default = "default_top_k")]
    pub top_k: usize,
    pub file_type: Option<String>,
    pub folder: Option<String>,
}

fn default_top_k() -> usize {
    20
}

#[derive(Debug, Serialize)]
pub struct EnrichedResult {
    pub doc_id: u64,
    pub path: String,
    pub filename: String,
    pub snippet: String,
    pub score: f64,
    pub file_type: String,
    pub modified: Option<String>,
    pub file_size: Option<i64>,
}

#[derive(Debug, Serialize)]
pub struct SearchResponse {
    pub results: Vec<EnrichedResult>,
    pub total: usize,
    pub elapsed_ms: f64,
}

async fn search_handler(
    State(state): State<Arc<AppState>>,
    Json(req): Json<SearchRequest>,
) -> Json<SearchResponse> {
    let start = std::time::Instant::now();

    // Embed query if embed_client is available
    let query_embedding = if let Some(ref embed_client) = state.embed_client {
        match embed_client.lock() {
            Ok(mut client) => match client.embed_query(&req.query) {
                Ok(embedding) => Some(embedding),
                Err(e) => {
                    warn!("Query embedding failed: {e}, falling back to BM25-only");
                    None
                }
            },
            Err(_) => None,
        }
    } else {
        None
    };

    let query = SearchQuery {
        text: req.query,
        top_k: Some(req.top_k),
        file_type: req.file_type,
        folder: req.folder,
    };

    let results = {
        let engine = state.search.read().unwrap();
        engine
            .search(&query, query_embedding.as_deref())
            .unwrap_or_default()
    };

    let store = state.store.lock().unwrap();
    let enriched: Vec<EnrichedResult> = results
        .into_iter()
        .map(|r| {
            let file_meta = store.get_file(&r.file_path).ok().flatten();
            EnrichedResult {
                doc_id: r.chunk_id,
                path: r.file_path.clone(),
                filename: r.file_name.clone(),
                snippet: r.snippet.plain,
                score: r.score,
                file_type: file_meta
                    .as_ref()
                    .map(|m| m.extension.clone())
                    .unwrap_or_default(),
                modified: file_meta.as_ref().map(|m| m.modified_at.clone()),
                file_size: file_meta.map(|m| m.size_bytes),
            }
        })
        .collect();
    drop(store);

    let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
    let total = enriched.len();

    Json(SearchResponse {
        results: enriched,
        total,
        elapsed_ms,
    })
}

pub fn router() -> Router<Arc<AppState>> {
    Router::new().route("/search", post(search_handler))
}
