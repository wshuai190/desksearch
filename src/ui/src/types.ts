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
}

export type TabId = 'search' | 'dashboard' | 'files' | 'folders' | 'settings';
