import type { SearchFilters } from '../types';

const FILE_TYPE_OPTIONS = [
  { value: 'pdf', label: 'PDF' },
  { value: 'txt', label: 'Text' },
  { value: 'md', label: 'Markdown' },
  { value: 'docx', label: 'Word' },
  { value: 'xlsx', label: 'Excel' },
  { value: 'py', label: 'Python' },
  { value: 'js', label: 'JavaScript' },
  { value: 'ts', label: 'TypeScript' },
  { value: 'html', label: 'HTML' },
  { value: 'eml', label: 'Email' },
];

interface FiltersProps {
  filters: SearchFilters;
  onFiltersChange: (filters: SearchFilters) => void;
  visible: boolean;
}

export default function Filters({ filters, onFiltersChange, visible }: FiltersProps) {
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

  const hasFilters = filters.file_types.length > 0 || filters.date_from || filters.date_to || filters.folder;

  return (
    <div className="w-56 flex-shrink-0 space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Filters</h3>
        {hasFilters && (
          <button
            onClick={clearFilters}
            className="text-xs text-accent-blue hover:text-accent-blue-hover"
          >
            Clear all
          </button>
        )}
      </div>

      <div>
        <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
          File Type
        </h4>
        <div className="space-y-1">
          {FILE_TYPE_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className="flex items-center gap-2 py-1 px-2 rounded hover:bg-gray-50 dark:hover:bg-dark-hover cursor-pointer"
            >
              <input
                type="checkbox"
                checked={filters.file_types.includes(opt.value)}
                onChange={() => toggleFileType(opt.value)}
                className="w-3.5 h-3.5 rounded border-gray-300 dark:border-dark-border text-accent-blue focus:ring-accent-blue/50 bg-transparent"
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">{opt.label}</span>
            </label>
          ))}
        </div>
      </div>

      <div>
        <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
          Date Range
        </h4>
        <div className="space-y-2">
          <input
            type="date"
            value={filters.date_from}
            onChange={(e) => onFiltersChange({ ...filters, date_from: e.target.value })}
            className="w-full text-sm px-2 py-1.5 rounded border border-gray-200 dark:border-dark-border
              bg-white dark:bg-dark-surface text-gray-700 dark:text-gray-300
              focus:outline-none focus:ring-1 focus:ring-accent-blue/50"
            placeholder="From"
          />
          <input
            type="date"
            value={filters.date_to}
            onChange={(e) => onFiltersChange({ ...filters, date_to: e.target.value })}
            className="w-full text-sm px-2 py-1.5 rounded border border-gray-200 dark:border-dark-border
              bg-white dark:bg-dark-surface text-gray-700 dark:text-gray-300
              focus:outline-none focus:ring-1 focus:ring-accent-blue/50"
            placeholder="To"
          />
        </div>
      </div>

      <div>
        <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
          Folder
        </h4>
        <input
          type="text"
          value={filters.folder}
          onChange={(e) => onFiltersChange({ ...filters, folder: e.target.value })}
          placeholder="e.g. ~/Documents"
          className="w-full text-sm px-2 py-1.5 rounded border border-gray-200 dark:border-dark-border
            bg-white dark:bg-dark-surface text-gray-700 dark:text-gray-300
            placeholder-gray-400 dark:placeholder-gray-500
            focus:outline-none focus:ring-1 focus:ring-accent-blue/50"
        />
      </div>
    </div>
  );
}
