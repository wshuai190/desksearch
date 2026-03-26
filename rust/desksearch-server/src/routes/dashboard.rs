//! Dashboard endpoint: GET /api/dashboard

use std::sync::Arc;

use axum::{
    extract::State,
    routing::get,
    Json, Router,
};
use serde::Serialize;

use crate::state::AppState;

#[derive(Debug, Serialize)]
pub struct DashboardResponse {
    pub total_files: i64,
    pub total_chunks: i64,
    pub has_dense_search: bool,
    pub uptime_secs: u64,
    pub version: String,
    pub engine: String,
}

async fn dashboard_handler(
    State(state): State<Arc<AppState>>,
) -> Json<DashboardResponse> {
    let (total_files, total_chunks) = {
        let store = state.store.lock().unwrap();
        let files = store.file_count().unwrap_or(0);
        let chunks = store.chunk_count().unwrap_or(0);
        (files, chunks)
    };

    let has_dense = {
        let engine = state.search.read().unwrap();
        engine.has_dense()
    };

    Json(DashboardResponse {
        total_files,
        total_chunks,
        has_dense_search: has_dense,
        uptime_secs: state.start_time.elapsed().as_secs(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        engine: "rust".to_string(),
    })
}

pub fn router() -> Router<Arc<AppState>> {
    Router::new().route("/dashboard", get(dashboard_handler))
}
