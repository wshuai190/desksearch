//! Settings endpoints:
//!   GET /api/settings — return current config
//!   PUT /api/settings — partial update config

use std::sync::Arc;

use axum::{
    extract::State,
    http::StatusCode,
    routing::get,
    Json, Router,
};
use serde_json::Value;

use crate::state::AppState;

async fn get_settings(State(state): State<Arc<AppState>>) -> Json<Value> {
    let config = std::fs::read_to_string(&state.config_path)
        .ok()
        .and_then(|s| serde_json::from_str::<Value>(&s).ok())
        .unwrap_or_else(|| Value::Object(serde_json::Map::new()));
    Json(config)
}

async fn put_settings(
    State(state): State<Arc<AppState>>,
    Json(updates): Json<Value>,
) -> Result<Json<Value>, StatusCode> {
    let mut config = std::fs::read_to_string(&state.config_path)
        .ok()
        .and_then(|s| serde_json::from_str::<Value>(&s).ok())
        .unwrap_or_else(|| Value::Object(serde_json::Map::new()));

    merge_json(&mut config, &updates);

    let json = serde_json::to_string_pretty(&config).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    if let Some(parent) = state.config_path.parent() {
        std::fs::create_dir_all(parent).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    }
    std::fs::write(&state.config_path, json).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok(Json(config))
}

fn merge_json(base: &mut Value, patch: &Value) {
    if let (Some(base_obj), Some(patch_obj)) = (base.as_object_mut(), patch.as_object()) {
        for (key, value) in patch_obj {
            let entry = base_obj.entry(key.clone()).or_insert(Value::Null);
            if value.is_object() && entry.is_object() {
                merge_json(entry, value);
            } else {
                *entry = value.clone();
            }
        }
    }
}

pub fn router() -> Router<Arc<AppState>> {
    Router::new().route("/settings", get(get_settings).put(put_settings))
}
