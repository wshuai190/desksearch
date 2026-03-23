import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../config';
import type { SearchFilters, FolderInfo } from '../types';

const FILE_TYPE_OPTIONS = [
  { value: 'pdf',  label: 'PDF',        icon: '📄' },
  { value: 'txt',  label: 'Text',       icon: '📝' },
  { value: 'md',   label: 'Markdown',   icon: '📝' },
  { value: 'docx', label: 'Word',       icon: '📄' },
  { value: 'xlsx', label: 'Excel',      icon: '📊' },
  { value: 'csv',  label: 'CSV',        icon: '📊' },
  { value: 'py',   label: 'Python',     icon: '🐍' },
  { value: 'js',   label: 'JavaScript', icon: '⚡' },
  { value: 'ts',   label: 'TypeScript', icon: '⚡' },
  { value: 'html', label: 'HTML',       icon: '🌐' },
  { value: 'json', label: 'JSON',       icon: '📋' },
  { value: 'eml',  label: 'Email',      icon: '✉️' },
  { value: 'ipynb',label: 'Notebook',   icon: '📓' },
];

interface FiltersProps {
  filters: SearchFilters;
  onFiltersChange: (filters: SearchFilters) => void;
  visible: boolean;
}

function shortenPath(path: string): string {
  return path.replace(/^\/Users\/[^/]+/, '~');
}

export default function Filters({ filters, onFiltersChange, visible }: FiltersProps) {
  const [watchedFolders, setWatchedFolders] = useState<FolderInfo[]>([]);

  useEffect(() => {
    if (!visible) return;
    fetch(`${API_BASE_URL}/api/folders`)
      .then(r => r.ok ? r.json() : [])
      .then((data: FolderInfo[]) => setWatchedFolders(data))
      .catch(() => {});
  }, [visible]);

  if (!visible) return null;

  const toggleFileType = (type: string) => {
    const types = filters.file_types.includes(type)
      ? filters.file_types.filter((t) => t !== type)
      : [...filters.file_types, type];
    onFiltersChange({ ...filters, file_types: types });
  };

  const clearFilters = () => {
    onFiltersChange({ file_types: [], date_from: '', date_to: '', folder: '' });
  };

  const hasFilters =
    filters.file_types.length > 0 || filters.date_from || filters.date_to || filters.folder;

  return (
    <div className="w-52 flex-shrink-0 space-y-5 animate-slideDown">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Filters</h3>
        {hasFilters && (
          <button
            onClick={clearFilters}
            className="text-xs text-accent-blue hover:text-accent-blue-hover transition-colors"
          >
            Clear all
          </button>
        )}
      </div>

      {/* File Type */}
      <div>
        <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
          File Type
        </h4>
        <div className="space-y-0.5 max-h-52 overflow-y-auto">
          {FILE_TYPE_OPTIONS.map((opt) => {
            const active = filters.file_types.includes(opt.value);
            return (
              <label
                key={opt.value}
                className={`flex items-center gap-2 py-1 px-2 rounded-lg cursor-pointer transition-colors ${
                  active
                    ? 'bg-accent-blue/10 text-accent-blue'
                    : 'hover:bg-gray-50 dark:hover:bg-dark-hover text-gray-700 dark:text-gray-300'
                }`}
              >
                <input
                  type="checkbox"
                  checked={active}
                  onChange={() => toggleFileType(opt.value)}
                  className="w-3.5 h-3.5 rounded border-gray-300 dark:border-dark-border text-accent-blue focus:ring-accent-blue/50 bg-transparent"
                />
                <span className="text-sm leading-none">{opt.icon}</span>
                <span className="text-sm">{opt.label}</span>
              </label>
            );
          })}
        </div>
      </div>

      {/* Date Range */}
      <div>
        <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
          Date Range
        </h4>
        <div className="space-y-2">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">From</label>
            <input
              type="date"
              value={filters.date_from}
              onChange={(e) => onFiltersChange({ ...filters, date_from: e.target.value })}
              className="w-full text-sm px-2 py-1.5 rounded-lg border border-gray-200 dark:border-dark-border
                bg-white dark:bg-dark-surface text-gray-700 dark:text-gray-300
                focus:outline-none focus:ring-1 focus:ring-accent-blue/50 focus:border-accent-blue
                transition-colors"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">To</label>
            <input
              type="date"
              value={filters.date_to}
              onChange={(e) => onFiltersChange({ ...filters, date_to: e.target.value })}
              className="w-full text-sm px-2 py-1.5 rounded-lg border border-gray-200 dark:border-dark-border
                bg-white dark:bg-dark-surface text-gray-700 dark:text-gray-300
                focus:outline-none focus:ring-1 focus:ring-accent-blue/50 focus:border-accent-blue
                transition-colors"
            />
          </div>
        </div>
      </div>

      {/* Folder */}
      <div>
        <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
          Folder
        </h4>
        {watchedFolders.length > 0 ? (
          <div className="space-y-0.5">
            <label
              className={`flex items-center gap-2 py-1 px-2 rounded-lg cursor-pointer transition-colors ${
                !filters.folder
                  ? 'bg-accent-blue/10 text-accent-blue'
                  : 'hover:bg-gray-50 dark:hover:bg-dark-hover text-gray-700 dark:text-gray-300'
              }`}
            >
              <input
                type="radio"
                name="folder"
                checked={!filters.folder}
                onChange={() => onFiltersChange({ ...filters, folder: '' })}
                className="w-3.5 h-3.5 text-accent-blue border-gray-300 focus:ring-accent-blue/50"
              />
              <span className="text-sm">All folders</span>
            </label>
            {watchedFolders.map(f => (
              <label
                key={f.path}
                className={`flex items-center gap-2 py-1 px-2 rounded-lg cursor-pointer transition-colors ${
                  filters.folder === f.path
                    ? 'bg-accent-blue/10 text-accent-blue'
                    : 'hover:bg-gray-50 dark:hover:bg-dark-hover text-gray-700 dark:text-gray-300'
                }`}
                title={f.path}
              >
                <input
                  type="radio"
                  name="folder"
                  checked={filters.folder === f.path}
                  onChange={() => onFiltersChange({ ...filters, folder: f.path })}
                  className="w-3.5 h-3.5 text-accent-blue border-gray-300 focus:ring-accent-blue/50 flex-shrink-0"
                />
                <span className="text-sm truncate">{shortenPath(f.path)}</span>
              </label>
            ))}
          </div>
        ) : (
          <input
            type="text"
            value={filters.folder}
            onChange={(e) => onFiltersChange({ ...filters, folder: e.target.value })}
            placeholder="e.g. ~/Documents"
            className="w-full text-sm px-2 py-1.5 rounded-lg border border-gray-200 dark:border-dark-border
              bg-white dark:bg-dark-surface text-gray-700 dark:text-gray-300
              placeholder-gray-400 dark:placeholder-gray-500
              focus:outline-none focus:ring-1 focus:ring-accent-blue/50 focus:border-accent-blue
              transition-colors"
          />
        )}
      </div>
    </div>
  );
}
