//! Search endpoint: POST /api/search

use std::sync::Arc;

use axum::{
    extract::State,
    routing::post,
    Json, Router,
};
use serde::{Deserialize, Serialize};

use crate::state::AppState;
use desksearch_core::{SearchQuery, SearchResult};

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
pub struct SearchResponse {
    pub results: Vec<SearchResult>,
    pub total: usize,
    pub elapsed_ms: f64,
}

async fn search_handler(
    State(state): State<Arc<AppState>>,
    Json(req): Json<SearchRequest>,
) -> Json<SearchResponse> {
    let start = std::time::Instant::now();

    let query = SearchQuery {
        text: req.query,
        top_k: Some(req.top_k),
        file_type: req.file_type,
        folder: req.folder,
    };

    let results = {
        let engine = state.search.read().unwrap();
        engine.search(&query).unwrap_or_default()
    };

    let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
    let total = results.len();

    Json(SearchResponse {
        results,
        total,
        elapsed_ms,
    })
}

pub fn router() -> Router<Arc<AppState>> {
    Router::new().route("/search", post(search_handler))
}
