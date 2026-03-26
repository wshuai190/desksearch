//! Configuration system for DeskSearch.
//! Loads from ~/.desksearch/config.json.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use tracing::{info, warn};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeskSearchConfig {
    /// HTTP server port.
    #[serde(default = "default_port")]
    pub port: u16,
    /// Data directory for indexes and metadata.
    #[serde(default)]
    pub data_dir: Option<PathBuf>,
    /// Embedding dimension (model-dependent).
    #[serde(default = "default_embedding_dim")]
    pub embedding_dim: usize,
    /// Number of embedding layers to use.
    #[serde(default = "default_embedding_layers")]
    pub embedding_layers: usize,
    /// Search speed preset: "fast", "balanced", or "precise".
    #[serde(default = "default_search_speed")]
    pub search_speed: String,
    /// Folders to watch for changes.
    #[serde(default)]
    pub watched_folders: Vec<String>,
    /// Folders config (for compatibility with existing folders endpoint).
    #[serde(default)]
    pub folders: Vec<FolderEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FolderEntry {
    pub path: String,
}

fn default_port() -> u16 {
    51983
}

fn default_embedding_dim() -> usize {
    384
}

fn default_embedding_layers() -> usize {
    6
}

fn default_search_speed() -> String {
    "balanced".to_string()
}

impl Default for DeskSearchConfig {
    fn default() -> Self {
        Self {
            port: default_port(),
            data_dir: None,
            embedding_dim: default_embedding_dim(),
            embedding_layers: default_embedding_layers(),
            search_speed: default_search_speed(),
            watched_folders: Vec::new(),
            folders: Vec::new(),
        }
    }
}

impl DeskSearchConfig {
    /// Load config from the standard location (~/.desksearch/config.json).
    pub fn load() -> Self {
        let config_path = dirs_next::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".desksearch")
            .join("config.json");
        Self::load_from(&config_path)
    }

    /// Load config from a specific path, falling back to defaults.
    pub fn load_from(path: &Path) -> Self {
        match std::fs::read_to_string(path) {
            Ok(contents) => match serde_json::from_str(&contents) {
                Ok(config) => {
                    info!("Loaded config from {}", path.display());
                    config
                }
                Err(e) => {
                    warn!("Failed to parse config {}: {e}, using defaults", path.display());
                    Self::default()
                }
            },
            Err(_) => {
                info!("No config at {}, using defaults", path.display());
                Self::default()
            }
        }
    }

    /// Save config to a specific path.
    pub fn save_to(&self, path: &Path) -> anyhow::Result<()> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let json = serde_json::to_string_pretty(self)?;
        std::fs::write(path, json)?;
        Ok(())
    }
}
