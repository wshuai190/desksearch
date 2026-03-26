//! Folder management endpoints:
//!   GET    /api/folders       — list watched folders
//!   POST   /api/folders       — add a folder
//!   DELETE /api/folders/:path — remove a folder

use std::sync::Arc;

use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};
use serde::{Deserialize, Serialize};

use crate::state::AppState;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct FolderEntry {
    pub path: String,
}

#[derive(Debug, Serialize, Deserialize, Default)]
struct Config {
    #[serde(default)]
    folders: Vec<FolderEntry>,
}

fn read_config(state: &AppState) -> Config {
    std::fs::read_to_string(&state.config_path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn write_config(state: &AppState, config: &Config) -> Result<(), StatusCode> {
    let json = serde_json::to_string_pretty(config).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    std::fs::write(&state.config_path, json).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)
}

async fn list_folders(State(state): State<Arc<AppState>>) -> Json<Vec<FolderEntry>> {
    Json(read_config(&state).folders)
}

#[derive(Debug, Deserialize)]
pub struct AddFolderRequest {
    pub path: String,
}

async fn add_folder(
    State(state): State<Arc<AppState>>,
    Json(req): Json<AddFolderRequest>,
) -> Result<(StatusCode, Json<Vec<FolderEntry>>), StatusCode> {
    let mut config = read_config(&state);

    if config.folders.iter().any(|f| f.path == req.path) {
        return Ok((StatusCode::OK, Json(config.folders)));
    }

    config.folders.push(FolderEntry { path: req.path });
    write_config(&state, &config)?;
    Ok((StatusCode::CREATED, Json(config.folders)))
}

async fn remove_folder(
    State(state): State<Arc<AppState>>,
    Path(encoded_path): Path<String>,
) -> Result<Json<Vec<FolderEntry>>, StatusCode> {
    let folder_path = urlencoding::decode(&encoded_path)
        .map_err(|_| StatusCode::BAD_REQUEST)?
        .into_owned();

    let mut config = read_config(&state);
    let before = config.folders.len();
    config.folders.retain(|f| f.path != folder_path);

    if config.folders.len() == before {
        return Err(StatusCode::NOT_FOUND);
    }

    write_config(&state, &config)?;
    Ok(Json(config.folders))
}

pub fn router() -> Router<Arc<AppState>> {
    Router::new()
        .route("/folders", get(list_folders).post(add_folder))
        .route("/folders/{path}", axum::routing::delete(remove_folder))
}
