//! Status endpoint: GET /api/status

use std::sync::Arc;

use axum::{
    extract::State,
    routing::get,
    Json, Router,
};
use serde::Serialize;

use crate::state::AppState;

#[derive(Debug, Serialize)]
pub struct StatusResponse {
    pub version: String,
    pub engine: String,
    pub total_files: i64,
    pub total_chunks: i64,
    pub status: String,
}

async fn status_handler(State(state): State<Arc<AppState>>) -> Json<StatusResponse> {
    let (files, chunks) = {
        let store = state.store.lock().unwrap();
        (
            store.file_count().unwrap_or(0),
            store.chunk_count().unwrap_or(0),
        )
    };

    Json(StatusResponse {
        version: env!("CARGO_PKG_VERSION").to_string(),
        engine: "rust".to_string(),
        total_files: files,
        total_chunks: chunks,
        status: "ready".to_string(),
    })
}

pub fn router() -> Router<Arc<AppState>> {
    Router::new().route("/status", get(status_handler))
}
