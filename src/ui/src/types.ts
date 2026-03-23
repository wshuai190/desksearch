export interface SearchResult {
  doc_id: string;
  path: string;
  filename: string;
  snippet: string;
  score: number;
  file_type: string;
  modified: string | null;
  file_size?: number;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  query_time_ms: number;
}

export interface IndexStatus {
  total_documents: number;
  total_chunks: number;
  index_size_mb: number;
  last_indexed: string | null;
  is_indexing: boolean;
}

export interface IndexingProgress {
  current: number;
  total: number;
  current_file: string;
  phase: string;
}

export interface SearchFilters {
  file_types: string[];
  date_from: string;
  date_to: string;
  folder: string;
}

export interface FolderInfo {
  path: string;
  file_count: number;
  last_indexed: string | null;
  status: string;
}

export interface FileInfo {
  doc_id: number;
  filename: string;
  path: string;
  file_type: string;
  size: number;
  modified: string | null;
  indexed_time: string | null;
  num_chunks: number;
}

export interface FilesResponse {
  files: FileInfo[];
  total: number;
  page: number;
  page_size: number;
}

export interface ActivityEntry {
  filename: string;
  path: string;
  indexed_time: string;
  file_type: string;
  num_chunks: number;
}

export interface DashboardStats {
  total_documents: number;
  total_chunks: number;
  index_size_mb: number;
  is_indexing: boolean;
  type_breakdown: Record<string, number>;
  watched_folders: FolderInfo[];
}

export interface SettingsData {
  data_dir: string;
  index_paths: string[];
  embedding_model: string;
  chunk_size: number;
  chunk_overlap: number;
  host: string;
  port: number;
  file_extensions: string[];
  max_file_size_mb: number;
  excluded_dirs: string[];
  // Integration fields
  api_key?: string | null;
  webhook_urls: string[];
  slack_webhook_url?: string | null;
}

export interface BrowserSyncResult {
  status: string;
  bookmarks_found: number;
  bookmarks_indexed: number;
  errors: number;
  message?: string;
}

export interface EmailImportResult {
  status: string;
  filename: string;
  emails_found: number;
  emails_indexed: number;
  errors: number;
}

export interface WebhookTestResult {
  status: string;
  url: string;
  http_status: number;
  delivered: boolean;
}

export type TabId = 'search' | 'dashboard' | 'files' | 'folders' | 'settings' | 'analytics' | 'topics' | 'duplicates';

// --- Killer feature types ---

export interface NLAnswer {
  answer: string;
  is_question: boolean;
}

export interface RelatedDoc {
  doc_id: number;
  similarity: number;
  path: string;
  filename: string;
}

export interface RichSearchResult extends SearchResult {
  related_docs: RelatedDoc[];
}

export interface RichSearchResponse {
  results: RichSearchResult[];
  total: number;
  query_time_ms: number;
  answer?: NLAnswer;
}

export interface SuggestResponse {
  suggestions: string[];
  recent: string[];
}

export interface RichPreview {
  doc_id: number;
  path: string;
  filename: string;
  file_type: string;
  preview_text: string;
  key_phrases: string[];
  size?: number;
  modified?: string;
  num_chunks: number;
  word_count: number;
}

export interface AnalyticsSummary {
  total_searches: number;
  total_clicks: number;
  top_searches: { query: string; count: number; avg_results: number }[];
  top_files: { path: string; filename: string; clicks: number }[];
  search_over_time: { date: string; count: number }[];
}

export interface TopicInfo {
  id: number;
  label: string;
  doc_count: number;
  doc_ids: number[];
  doc_filenames: string[];
  doc_paths: string[];
}

export interface CollectionsResponse {
  topics: TopicInfo[];
  total_docs_clustered: number;
}

export interface DuplicatePair {
  doc_id_a: number;
  doc_id_b: number;
  similarity: number;
  path_a: string;
  path_b: string;
  filename_a: string;
  filename_b: string;
}

export interface DuplicatesResponse {
  pairs: DuplicatePair[];
  total: number;
}
