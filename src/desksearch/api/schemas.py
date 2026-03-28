"""Pydantic models for the DeskSearch API."""
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Search query parameters."""

    query: str = Field(..., min_length=1, description="Search query string")
    filters: Optional[dict[str, str]] = Field(
        default=None,
        description="Optional filters: file_type, date_from, date_to, path",
    )
    limit: int = Field(default=20, ge=1, le=100, description="Max results to return")


class SearchResult(BaseModel):
    """A single search result."""

    doc_id: str = Field(..., description="Unique document identifier")
    path: str = Field(..., description="Full file path")
    filename: str = Field(..., description="File name")
    snippet: str = Field(..., description="Relevant text snippet with highlights")
    score: float = Field(..., description="Relevance score (0-1)")
    file_type: str = Field(..., description="File extension without dot")
    modified: Optional[datetime] = Field(
        default=None, description="Last modified timestamp"
    )
    other_chunk_count: int = Field(
        default=0,
        description="Number of additional matching chunks from the same file that were deduplicated",
    )
    file_size: Optional[int] = Field(
        default=None, description="File size in bytes"
    )


class SearchResponse(BaseModel):
    """Response for a search query."""

    results: list[SearchResult] = Field(default_factory=list)
    total: int = Field(default=0, description="Total matching documents")
    query_time_ms: float = Field(
        default=0.0, description="Time taken to execute search in milliseconds"
    )


class IndexStatus(BaseModel):
    """Current index statistics."""

    total_documents: int = Field(default=0, description="Number of indexed documents")
    total_chunks: int = Field(default=0, description="Number of indexed chunks")
    index_size_mb: float = Field(default=0.0, description="Total index size in MB")
    last_indexed: Optional[datetime] = Field(
        default=None, description="Timestamp of last indexing run"
    )
    is_indexing: bool = Field(default=False, description="Whether indexing is in progress")


class IndexRequest(BaseModel):
    """Request to index specific paths.

    If ``paths`` is omitted or empty, the server will index all configured
    ``index_paths`` from settings.
    """

    paths: list[str] = Field(
        default_factory=list, description="List of file or directory paths to index (empty = use configured folders)"
    )


class SettingsResponse(BaseModel):
    """Current configuration exposed via the API."""

    data_dir: str
    index_paths: list[str]
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    search_speed: str = "regular"
    host: str
    port: int
    file_extensions: list[str]
    max_file_size_mb: int
    excluded_dirs: list[str]
    # Integration fields (optional — None when not configured)
    api_key: Optional[str] = None
    webhook_urls: list[str] = Field(default_factory=list)
    slack_webhook_url: Optional[str] = None


class SettingsUpdateRequest(BaseModel):
    """Partial config update — all fields optional."""

    index_paths: Optional[list[str]] = None
    chunk_size: Optional[int] = Field(default=None, ge=64, le=4096)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=512)
    search_speed: Optional[str] = Field(default=None, description="Speed tier: fast, regular, or pro")
    file_extensions: Optional[list[str]] = None
    max_file_size_mb: Optional[int] = Field(default=None, ge=1, le=1024)
    excluded_dirs: Optional[list[str]] = None
    # Integration fields
    api_key: Optional[str] = None          # empty string clears the key
    webhook_urls: Optional[list[str]] = None
    slack_webhook_url: Optional[str] = None  # empty string clears


class FolderInfo(BaseModel):
    """Information about a watched folder."""

    path: str
    file_count: int = 0
    last_indexed: Optional[datetime] = None
    status: str = "watching"


class FolderAddRequest(BaseModel):
    """Request to add a watched folder."""

    path: str = Field(..., min_length=1, description="Directory path to watch")


class FileInfo(BaseModel):
    """Information about an indexed file."""

    doc_id: int
    filename: str
    path: str
    file_type: str
    size: int
    modified: Optional[datetime] = None
    indexed_time: Optional[datetime] = None
    num_chunks: int = 0


class FilesResponse(BaseModel):
    """Paginated list of indexed files."""

    files: list[FileInfo] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50


class FilePreview(BaseModel):
    """Preview of a file's content."""

    doc_id: int
    path: str
    filename: str
    content: str
    num_chunks: int = 0


class ActivityEntry(BaseModel):
    """A recent indexing activity entry."""

    filename: str
    path: str
    indexed_time: datetime
    file_type: str
    num_chunks: int


class ActivityResponse(BaseModel):
    """Recent indexing activity."""

    entries: list[ActivityEntry] = Field(default_factory=list)


class DashboardStats(BaseModel):
    """Dashboard statistics."""

    total_documents: int = 0
    total_chunks: int = 0
    index_size_mb: float = 0.0
    is_indexing: bool = False
    type_breakdown: dict[str, int] = Field(default_factory=dict)
    watched_folders: list[FolderInfo] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str


# ---------------------------------------------------------------------------
# New killer feature schemas
# ---------------------------------------------------------------------------

class NLAnswer(BaseModel):
    """Extractive answer for a natural language question."""
    answer: str
    is_question: bool = True


class SuggestResponse(BaseModel):
    """Autocomplete suggestions for a partial query."""
    suggestions: list[str] = Field(default_factory=list)
    recent: list[str] = Field(default_factory=list)


class RichSearchResult(SearchResult):
    """Extended search result with related docs."""
    related_docs: list[dict] = Field(default_factory=list)


class RichSearchResponse(BaseModel):
    """Search response with optional NL answer and rich results."""
    results: list[RichSearchResult] = Field(default_factory=list)
    total: int = Field(default=0)
    query_time_ms: float = Field(default=0.0)
    answer: Optional[NLAnswer] = Field(default=None)


class RichPreview(BaseModel):
    """Rich document preview with key phrases and metadata."""
    doc_id: int
    path: str
    filename: str
    file_type: str
    preview_text: str
    key_phrases: list[str] = Field(default_factory=list)
    size: Optional[int] = None
    modified: Optional[datetime] = None
    num_chunks: int = 0
    word_count: int = 0


class AnalyticsSummary(BaseModel):
    """Search analytics summary."""
    total_searches: int = 0
    total_clicks: int = 0
    top_searches: list[dict] = Field(default_factory=list)
    top_files: list[dict] = Field(default_factory=list)
    search_over_time: list[dict] = Field(default_factory=list)


class TopicInfo(BaseModel):
    """A topic / smart collection."""
    id: int
    label: str
    doc_count: int
    doc_ids: list[int] = Field(default_factory=list)
    doc_filenames: list[str] = Field(default_factory=list)
    doc_paths: list[str] = Field(default_factory=list)


class CollectionsResponse(BaseModel):
    """Smart document collections."""
    topics: list[TopicInfo] = Field(default_factory=list)
    total_docs_clustered: int = 0


class DuplicatePair(BaseModel):
    """A pair of potentially duplicate documents."""
    doc_id_a: int
    doc_id_b: int
    similarity: float
    path_a: str
    path_b: str
    filename_a: str
    filename_b: str


class DuplicatesResponse(BaseModel):
    """Duplicate file detection results."""
    pairs: list[DuplicatePair] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Search history, favorites, and recent opens
# ---------------------------------------------------------------------------

class SearchHistoryEntry(BaseModel):
    """A single search history entry."""
    query: str
    result_count: int = 0
    searched_at: datetime

class SearchHistoryResponse(BaseModel):
    """Search history listing."""
    entries: list[SearchHistoryEntry] = Field(default_factory=list)

class FavoriteEntry(BaseModel):
    """A favorited file."""
    doc_id: int
    path: str
    filename: str
    file_type: str
    size: int
    modified: Optional[datetime] = None
    created_at: datetime

class FavoritesResponse(BaseModel):
    """List of favorited files."""
    favorites: list[FavoriteEntry] = Field(default_factory=list)

class RecentOpenEntry(BaseModel):
    """A recently opened file."""
    doc_id: int
    path: str
    filename: str
    file_type: str
    size: int
    modified: Optional[datetime] = None
    opened_at: datetime

class RecentOpensResponse(BaseModel):
    """List of recently opened files."""
    entries: list[RecentOpenEntry] = Field(default_factory=list)
