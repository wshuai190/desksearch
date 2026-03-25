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
use tracing::info;
use tracing_subscriber::EnvFilter;

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
    info!("Indexing directory: {}", path.display());

    let walker = desksearch_indexer::FileWalker::new(vec![path.clone()]);
    let result = walker.walk()?;

    info!(
        "Found {} files ({} skipped) in {}ms",
        result.files.len(),
        result.skipped,
        result.elapsed_ms
    );

    // TODO: Parse, chunk, and index each file
    info!("Indexing pipeline not yet implemented — files discovered only");

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
