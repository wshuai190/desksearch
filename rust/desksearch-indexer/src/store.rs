//! SQLite metadata store for indexed documents and chunks.
//!
//! Stores file metadata (path, hash, size, timestamps) and chunk
//! information. Compatible with the existing Python DeskSearch schema.

use std::path::Path;

use anyhow::{Context, Result};
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use tracing::info;

/// Metadata for an indexed file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileMeta {
    pub id: i64,
    pub path: String,
    pub filename: String,
    pub extension: String,
    pub size_bytes: i64,
    pub content_hash: String,
    pub modified_at: String,
    pub indexed_at: String,
    pub chunk_count: i64,
}

/// Metadata for a text chunk.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChunkMeta {
    pub id: i64,
    pub file_id: i64,
    pub chunk_index: i64,
    pub text: String,
    pub char_offset: i64,
}

/// SQLite metadata store.
pub struct MetadataStore {
    conn: Connection,
}

impl MetadataStore {
    /// Open or create the metadata database.
    pub fn open(db_path: &Path) -> Result<Self> {
        if let Some(parent) = db_path.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("Failed to create dir: {}", parent.display()))?;
        }

        let conn = Connection::open(db_path)
            .with_context(|| format!("Failed to open database: {}", db_path.display()))?;

        // Enable WAL mode for better concurrent read/write performance
        conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;")?;

        let store = Self { conn };
        store.init_schema()?;

        info!("Metadata store opened at {}", db_path.display());
        Ok(store)
    }

    /// Open an in-memory database (for testing).
    pub fn open_memory() -> Result<Self> {
        let conn = Connection::open_in_memory()?;
        let store = Self { conn };
        store.init_schema()?;
        Ok(store)
    }

    fn init_schema(&self) -> Result<()> {
        self.conn.execute_batch(
            "
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL,
                extension TEXT NOT NULL DEFAULT '',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                content_hash TEXT NOT NULL DEFAULT '',
                modified_at TEXT NOT NULL DEFAULT '',
                indexed_at TEXT NOT NULL DEFAULT (datetime('now')),
                chunk_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                char_offset INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
            CREATE INDEX IF NOT EXISTS idx_files_hash ON files(content_hash);
            CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks(file_id);
            ",
        )?;
        Ok(())
    }

    /// Insert or update a file record. Returns the file ID.
    pub fn upsert_file(
        &self,
        path: &str,
        filename: &str,
        extension: &str,
        size_bytes: i64,
        content_hash: &str,
        modified_at: &str,
    ) -> Result<i64> {
        self.conn.execute(
            "INSERT INTO files (path, filename, extension, size_bytes, content_hash, modified_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)
             ON CONFLICT(path) DO UPDATE SET
                filename = excluded.filename,
                extension = excluded.extension,
                size_bytes = excluded.size_bytes,
                content_hash = excluded.content_hash,
                modified_at = excluded.modified_at,
                indexed_at = datetime('now')",
            params![path, filename, extension, size_bytes, content_hash, modified_at],
        )?;

        Ok(self.conn.last_insert_rowid())
    }

    /// Insert a chunk record. Returns the chunk ID.
    pub fn insert_chunk(
        &self,
        file_id: i64,
        chunk_index: i64,
        text: &str,
        char_offset: i64,
    ) -> Result<i64> {
        self.conn.execute(
            "INSERT INTO chunks (file_id, chunk_index, text, char_offset) VALUES (?1, ?2, ?3, ?4)",
            params![file_id, chunk_index, text, char_offset],
        )?;
        Ok(self.conn.last_insert_rowid())
    }

    /// Delete all chunks for a file.
    pub fn delete_chunks_for_file(&self, file_id: i64) -> Result<()> {
        self.conn
            .execute("DELETE FROM chunks WHERE file_id = ?1", params![file_id])?;
        Ok(())
    }

    /// Delete a file and its chunks.
    pub fn delete_file(&self, path: &str) -> Result<()> {
        self.conn
            .execute("DELETE FROM files WHERE path = ?1", params![path])?;
        Ok(())
    }

    /// Get a file record by path.
    pub fn get_file(&self, path: &str) -> Result<Option<FileMeta>> {
        let mut stmt = self
            .conn
            .prepare("SELECT id, path, filename, extension, size_bytes, content_hash, modified_at, indexed_at, chunk_count FROM files WHERE path = ?1")?;

        let result = stmt
            .query_row(params![path], |row| {
                Ok(FileMeta {
                    id: row.get(0)?,
                    path: row.get(1)?,
                    filename: row.get(2)?,
                    extension: row.get(3)?,
                    size_bytes: row.get(4)?,
                    content_hash: row.get(5)?,
                    modified_at: row.get(6)?,
                    indexed_at: row.get(7)?,
                    chunk_count: row.get(8)?,
                })
            })
            .optional()?;

        Ok(result)
    }

    /// Check if a file needs reindexing (hash changed).
    pub fn needs_reindex(&self, path: &str, content_hash: &str) -> Result<bool> {
        match self.get_file(path)? {
            None => Ok(true), // New file
            Some(meta) => Ok(meta.content_hash != content_hash),
        }
    }

    /// Get total file count.
    pub fn file_count(&self) -> Result<i64> {
        let count: i64 = self
            .conn
            .query_row("SELECT COUNT(*) FROM files", [], |row| row.get(0))?;
        Ok(count)
    }

    /// Get total chunk count.
    pub fn chunk_count(&self) -> Result<i64> {
        let count: i64 = self
            .conn
            .query_row("SELECT COUNT(*) FROM chunks", [], |row| row.get(0))?;
        Ok(count)
    }

    /// Get chunk text by chunk ID.
    pub fn get_chunk_text(&self, chunk_id: i64) -> Result<Option<String>> {
        let result: Option<String> = self
            .conn
            .query_row(
                "SELECT text FROM chunks WHERE id = ?1",
                params![chunk_id],
                |row| row.get(0),
            )
            .optional()?;
        Ok(result)
    }

    /// Get file path for a chunk ID.
    pub fn get_file_path_for_chunk(&self, chunk_id: i64) -> Result<Option<String>> {
        let result: Option<String> = self
            .conn
            .query_row(
                "SELECT f.path FROM files f JOIN chunks c ON c.file_id = f.id WHERE c.id = ?1",
                params![chunk_id],
                |row| row.get(0),
            )
            .optional()?;
        Ok(result)
    }
}

// Bring in rusqlite's OptionalExtension
use rusqlite::OptionalExtension;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_create_and_query() -> Result<()> {
        let store = MetadataStore::open_memory()?;

        let file_id = store.upsert_file(
            "/tmp/test.txt",
            "test.txt",
            "txt",
            1024,
            "abc123",
            "2026-03-25",
        )?;
        assert!(file_id > 0);

        let chunk_id = store.insert_chunk(file_id, 0, "Hello, world!", 0)?;
        assert!(chunk_id > 0);

        assert_eq!(store.file_count()?, 1);
        assert_eq!(store.chunk_count()?, 1);

        let file = store.get_file("/tmp/test.txt")?;
        assert!(file.is_some());
        assert_eq!(file.unwrap().filename, "test.txt");

        Ok(())
    }

    #[test]
    fn test_needs_reindex() -> Result<()> {
        let store = MetadataStore::open_memory()?;

        assert!(store.needs_reindex("/tmp/test.txt", "hash1")?);

        store.upsert_file("/tmp/test.txt", "test.txt", "txt", 100, "hash1", "2026-03-25")?;

        assert!(!store.needs_reindex("/tmp/test.txt", "hash1")?);
        assert!(store.needs_reindex("/tmp/test.txt", "hash2")?);

        Ok(())
    }

    #[test]
    fn test_delete_file() -> Result<()> {
        let store = MetadataStore::open_memory()?;

        let file_id = store.upsert_file("/tmp/test.txt", "test.txt", "txt", 100, "h", "d")?;
        store.insert_chunk(file_id, 0, "chunk1", 0)?;
        store.insert_chunk(file_id, 1, "chunk2", 100)?;

        assert_eq!(store.chunk_count()?, 2);

        store.delete_file("/tmp/test.txt")?;
        assert_eq!(store.file_count()?, 0);
        // Chunks should be cascade-deleted
        assert_eq!(store.chunk_count()?, 0);

        Ok(())
    }
}
