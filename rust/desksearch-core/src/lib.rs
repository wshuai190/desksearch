pub mod bm25;
pub mod fusion;
pub mod search;
pub mod snippets;

// Re-export main types
pub use search::{SearchEngine, SearchResult, SearchQuery, SearchConfig};
pub use fusion::FusedResult;
pub use snippets::Snippet;
