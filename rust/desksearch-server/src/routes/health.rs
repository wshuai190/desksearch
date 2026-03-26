//! Health endpoint: GET /api/health

use std::sync::Arc;

use axum::{extract::State, routing::get, Json, Router};
use serde::Serialize;

use crate::state::AppState;

#[derive(Debug, Serialize)]
pub struct HealthResponse {
    pub status: &'static str,
    pub version: &'static str,
    pub engine: &'static str,
    pub uptime_secs: u64,
}

async fn health_handler(State(state): State<Arc<AppState>>) -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok",
        version: env!("CARGO_PKG_VERSION"),
        engine: "rust",
        uptime_secs: state.start_time.elapsed().as_secs(),
    })
}

pub fn router() -> Router<Arc<AppState>> {
    Router::new().route("/health", get(health_handler))
}
