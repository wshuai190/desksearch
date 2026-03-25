//! API route handlers.

mod search;
mod status;

use std::sync::Arc;
use axum::Router;
use crate::state::AppState;

/// Build the API router with all endpoints.
pub fn api_router(state: Arc<AppState>) -> Router {
    Router::new()
        .merge(search::router())
        .merge(status::router())
        .with_state(state)
}
