//! DeskSearch — Private semantic search engine for your files.
//!
//! Rust-powered backend with axum HTTP server.

mod routes;
mod state;

use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use anyhow::Result;
use axum::Router;
use clap::{Parser, Subcommand};
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;
use tracing::{info, warn};
use tracing_subscriber::EnvFilter;

use desksearch_indexer::{ChunkerConfig, FileWalker};
use desksearch_indexer::parsers;

use state::AppState;

#[derive(Parser)]
#[command(name = "desksearch", about = "Private semantic search for your files")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Start the DeskSearch server.
    Serve {
        /// Port to listen on.
        #[arg(short, long, default_value = "51983")]
        port: u16,
        /// Data directory for indexes and metadata.
        #[arg(short, long)]
        data_dir: Option<PathBuf>,
    },
    /// Index files in the specified directory.
    Index {
        /// Directory to index.
        path: PathBuf,
        /// Data directory for indexes and metadata.
        #[arg(short, long)]
        data_dir: Option<PathBuf>,
    },
    /// Show index status and statistics.
    Status {
        /// Data directory for indexes and metadata.
        #[arg(short, long)]
        data_dir: Option<PathBuf>,
    },
}

fn default_data_dir() -> PathBuf {
    dirs_next::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".desksearch")
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    let cli = Cli::parse();

    match cli.command {
        Commands::Serve { port, data_dir } => {
            let data_dir = data_dir.unwrap_or_else(default_data_dir);
            serve(port, data_dir).await?;
        }
        Commands::Index { path, data_dir } => {
            let data_dir = data_dir.unwrap_or_else(default_data_dir);
            index_directory(&path, &data_dir)?;
        }
        Commands::Status { data_dir } => {
            let data_dir = data_dir.unwrap_or_else(default_data_dir);
            show_status(&data_dir)?;
        }
    }

    Ok(())
}

async fn serve(port: u16, data_dir: PathBuf) -> Result<()> {
    info!("Starting DeskSearch server on port {port}");
    info!("Data directory: {}", data_dir.display());

    let state = Arc::new(AppState::new(&data_dir)?);

    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    let app = Router::new()
        .nest("/api", routes::api_router(state.clone()))
        .layer(cors)
        .layer(TraceLayer::new_for_http());

    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    info!("DeskSearch ready at http://{addr}");

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}

fn index_directory(path: &PathBuf, data_dir: &PathBuf) -> Result<()> {
    use desksearch_core::SearchConfig;
    use desksearch_indexer::MetadataStore;

    info!("Indexing directory: {}", path.display());

    let walker = FileWalker::new(vec![path.clone()]);
    let result = walker.walk()?;

    info!(
        "Found {} files ({} skipped) in {}ms",
        result.files.len(),
        result.skipped,
        result.elapsed_ms
    );

    // Open stores
    std::fs::create_dir_all(data_dir)?;
    let index_dir = data_dir.join("index");
    let db_path = data_dir.join("metadata.db");

    let engine = desksearch_core::SearchEngine::new(&index_dir, SearchConfig::default())?;
    let store = MetadataStore::open(&db_path)?;
    let chunker_config = ChunkerConfig::default();
    let mut writer = engine.bm25().writer(50)?;

    let mut indexed = 0usize;
    let mut skipped = result.skipped;

    for file_path in &result.files {
        let path_str = file_path.to_string_lossy();

        // Parse file content
        let text = match parsers::parse_file(file_path) {
            Ok(Some(text)) => text,
            Ok(None) => {
                skipped += 1;
                continue;
            }
            Err(e) => {
                warn!("Failed to parse {}: {e}", path_str);
                skipped += 1;
                continue;
            }
        };

        // Get file metadata
        let metadata = std::fs::metadata(file_path).ok();
        let file_name = file_path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();
        let extension = file_path
            .extension()
            .map(|e| e.to_string_lossy().to_string())
            .unwrap_or_default();
        let size_bytes = metadata.as_ref().map(|m| m.len() as i64).unwrap_or(0);
        let modified_time = metadata
            .as_ref()
            .and_then(|m| m.modified().ok())
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0);

        // Content hash for dedup
        let content_hash = {
            use std::hash::{Hash, Hasher};
            let mut hasher = std::collections::hash_map::DefaultHasher::new();
            text.as_bytes().hash(&mut hasher);
            format!("{:x}", hasher.finish())
        };

        // Skip if unchanged
        if !store.needs_reindex(&path_str, &content_hash)? {
            continue;
        }

        // Upsert file record
        let doc_id = store.upsert_file(
            &path_str,
            &file_name,
            &extension,
            size_bytes,
            &content_hash,
            modified_time,
        )?;

        // Replace chunks
        let _ = store.delete_chunks_for_doc(doc_id);
        engine.bm25().delete_by_path(&mut writer, &path_str);

        let chunks = desksearch_indexer::chunker::chunk_text(&text, &chunker_config);
        for chunk in &chunks {
            let chunk_id = store.insert_chunk(doc_id, chunk.index as i64, &chunk.text, chunk.offset as i64)?;
            engine.bm25().add_chunk(&mut writer, chunk_id as u64, &chunk.text, &path_str)?;
        }

        indexed += 1;
    }

    writer.commit()?;

    info!("Indexed {indexed} files ({skipped} skipped)");
    println!("Indexed {indexed} files ({skipped} skipped)");
    println!("Total files: {}", store.file_count()?);
    println!("Total chunks: {}", store.chunk_count()?);

    Ok(())
}

fn show_status(data_dir: &PathBuf) -> Result<()> {
    let db_path = data_dir.join("metadata.db");
    if !db_path.exists() {
        println!("No DeskSearch index found at {}", data_dir.display());
        return Ok(());
    }

    let store = desksearch_indexer::MetadataStore::open(&db_path)?;
    println!("DeskSearch Index Status");
    println!("=======================");
    println!("Data directory: {}", data_dir.display());
    println!("Files indexed:  {}", store.file_count()?);
    println!("Total chunks:   {}", store.chunk_count()?);

    Ok(())
}
