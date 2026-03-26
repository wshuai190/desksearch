//! API route handlers.

mod dashboard;
mod folders;
mod health;
mod index;
mod search;
mod settings;
mod status;

use std::sync::Arc;
use axum::Router;
use crate::state::AppState;

/// Build the API router with all endpoints.
pub fn api_router(state: Arc<AppState>) -> Router {
    Router::new()
        .merge(search::router())
        .merge(status::router())
        .merge(health::router())
        .merge(index::router())
        .merge(folders::router())
        .merge(settings::router())
        .merge(dashboard::router())
        .with_state(state)
}
