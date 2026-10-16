/**
 * `filters` namespace (en).
 *
 * Flat { key: string } map; the `filters.` prefix is added automatically by
 * locales/index.ts, so components call `t('filters.<key>')`.
 */
export default {
  // Panel
  'title': 'Filters',

  // File type
  'fileType': 'File Type',
  'type.pdf': 'PDF',
  'type.txt': 'Text',
  'type.md': 'Markdown',
  'type.docx': 'Word',
  'type.xlsx': 'Excel',
  'type.csv': 'CSV',
  'type.py': 'Python',
  'type.js': 'JavaScript',
  'type.ts': 'TypeScript',
  'type.html': 'HTML',
  'type.json': 'JSON',
  'type.eml': 'Email',
  'type.ipynb': 'Notebook',

  // Date range
  'dateRange': 'Date Range',
  'from': 'From',
  'to': 'To',

  // Folder
  'folder': 'Folder',
  'allFolders': 'All folders',
  'folderPlaceholder': 'e.g. ~/Documents',

  // AI answer banner
  'answer.title': 'AI Answer',
  'answer.extracted': 'Extracted from your documents',
  'answer.copy': 'Copy answer',
  'answer.scrollHint': 'Scroll down to see source documents',
} as const;
