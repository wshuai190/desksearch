//! BM25 full-text search powered by tantivy.
//!
//! Wraps tantivy's index to provide document indexing and BM25 search
//! with minimal overhead. The index is persisted to disk and supports
//! incremental updates.

use std::path::Path;

use anyhow::{Context, Result};
use tantivy::collector::TopDocs;
use tantivy::query::QueryParser;
use tantivy::schema::*;
use tantivy::{doc, Index, IndexReader, IndexWriter, ReloadPolicy};
use tracing::{debug, info};

/// A scored document from BM25 search.
#[derive(Debug, Clone)]
pub struct BM25Result {
    /// Internal document ID (matches chunk_id in SQLite).
    pub doc_id: u64,
    /// BM25 relevance score.
    pub score: f32,
    /// The text content of the chunk (for snippet extraction).
    pub text: String,
    /// The file path this chunk belongs to.
    pub path: String,
}

/// BM25 search index backed by tantivy.
pub struct BM25Index {
    index: Index,
    pub reader: IndexReader,
    #[allow(dead_code)]
    schema: Schema,
    /// Field for the chunk text content.
    text_field: Field,
    /// Field for the unique chunk ID.
    id_field: Field,
    /// Field for the file path.
    path_field: Field,
}

impl BM25Index {
    /// Open or create a BM25 index at the given directory.
    pub fn open_or_create(index_dir: &Path) -> Result<Self> {
        std::fs::create_dir_all(index_dir)
            .with_context(|| format!("Failed to create index dir: {}", index_dir.display()))?;

        let mut schema_builder = Schema::builder();
        let id_field = schema_builder.add_u64_field("chunk_id", INDEXED | STORED | FAST);
        let text_field = schema_builder.add_text_field("text", TEXT | STORED);
        let path_field = schema_builder.add_text_field("path", STRING | STORED);
        let schema = schema_builder.build();

        let index = Index::open_or_create(
            tantivy::directory::MmapDirectory::open(index_dir)
                .with_context(|| "Failed to open mmap directory")?,
            schema.clone(),
        )
        .with_context(|| "Failed to open or create tantivy index")?;

        let reader = index
            .reader_builder()
            .reload_policy(ReloadPolicy::OnCommitWithDelay)
            .try_into()
            .with_context(|| "Failed to create index reader")?;

        info!("BM25 index opened at {}", index_dir.display());

        Ok(Self {
            index,
            reader,
            schema,
            text_field,
            id_field,
            path_field,
        })
    }

    /// Get a writer for batch indexing operations.
    pub fn writer(&self, heap_size_mb: usize) -> Result<IndexWriter> {
        self.index
            .writer(heap_size_mb * 1_000_000)
            .with_context(|| "Failed to create index writer")
    }

    /// Add a document chunk to the index.
    pub fn add_chunk(
        &self,
        writer: &mut IndexWriter,
        chunk_id: u64,
        text: &str,
        path: &str,
    ) -> Result<()> {
        writer.add_document(doc!(
            self.id_field => chunk_id,
            self.text_field => text,
            self.path_field => path,
        ))?;
        Ok(())
    }

    /// Delete all chunks for a given file path.
    pub fn delete_by_path(&self, writer: &mut IndexWriter, path: &str) {
        let term = Term::from_field_text(self.path_field, path);
        writer.delete_term(term);
    }

    /// Search the index and return top-k results.
    pub fn search(&self, query_str: &str, top_k: usize) -> Result<Vec<BM25Result>> {
        let searcher = self.reader.searcher();
        let query_parser = QueryParser::for_index(&self.index, vec![self.text_field]);

        let query = query_parser
            .parse_query(query_str)
            .with_context(|| format!("Failed to parse query: {query_str}"))?;

        let top_docs = searcher
            .search(&query, &TopDocs::with_limit(top_k))
            .with_context(|| "Search execution failed")?;

        let mut results = Vec::with_capacity(top_docs.len());
        for (score, doc_addr) in top_docs {
            let doc: TantivyDocument = searcher
                .doc(doc_addr)
                .with_context(|| "Failed to retrieve document")?;

            let doc_id = doc
                .get_first(self.id_field)
                .and_then(|v| v.as_u64())
                .unwrap_or(0);

            let text = doc
                .get_first(self.text_field)
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();

            let path = doc
                .get_first(self.path_field)
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();

            results.push(BM25Result {
                doc_id,
                score,
                text,
                path,
            });
        }

        debug!(
            query = query_str,
            results = results.len(),
            "BM25 search completed"
        );

        Ok(results)
    }

    /// Get total number of documents in the index.
    pub fn num_docs(&self) -> u64 {
        self.reader.searcher().num_docs()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_index_and_search() -> Result<()> {
        let tmp = TempDir::new()?;
        let idx = BM25Index::open_or_create(tmp.path())?;
        let mut writer = idx.writer(15)?;

        idx.add_chunk(&mut writer, 1, "Rust is a systems programming language", "/doc1.txt")?;
        idx.add_chunk(&mut writer, 2, "Python is great for machine learning", "/doc2.txt")?;
        idx.add_chunk(
            &mut writer,
            3,
            "Semantic search finds documents by meaning",
            "/doc3.txt",
        )?;

        writer.commit()?;
        idx.reader.reload()?;

        let results = idx.search("rust programming", 10)?;
        assert!(!results.is_empty(), "Should find results for 'rust programming'");
        assert_eq!(results[0].doc_id, 1, "First result should be doc1");

        let results = idx.search("machine learning", 10)?;
        assert!(!results.is_empty());
        assert_eq!(results[0].doc_id, 2);

        Ok(())
    }

    #[test]
    fn test_delete_by_path() -> Result<()> {
        let tmp = TempDir::new()?;
        let idx = BM25Index::open_or_create(tmp.path())?;
        let mut writer = idx.writer(15)?;

        idx.add_chunk(&mut writer, 1, "Hello world from doc1", "/doc1.txt")?;
        idx.add_chunk(&mut writer, 2, "Hello world from doc2", "/doc2.txt")?;
        writer.commit()?;
        idx.reader.reload()?;

        assert_eq!(idx.num_docs(), 2);

        // Reuse the same writer (can't create a second one while first is alive)
        idx.delete_by_path(&mut writer, "/doc1.txt");
        writer.commit()?;
        idx.reader.reload()?;

        assert_eq!(idx.num_docs(), 1);

        Ok(())
    }
}
