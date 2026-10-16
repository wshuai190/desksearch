/**
 * results namespace (en).
 *
 * Flat { key: string } map; the `results.` prefix is added automatically by
 * locales/index.ts, so components call `t('results.<key>')`.
 *
 * Generic words (open, preview, copy, loading, result counts, …) live in
 * `common.ts` and are reused instead of being redefined here.
 */
export default {
  // Result count + query timing
  'countLabel': '{count} results',
  'countLabel_one': '{count} result',
  'timeMs': '{ms}ms',
  'timeSeconds': '{seconds}s',

  // Sort options
  'sortRelevance': 'Relevance',
  'sortDateNewest': 'Date (newest)',
  'sortDateOldest': 'Date (oldest)',
  'sortSizeLargest': 'Size (largest)',
  'sortSizeSmallest': 'Size (smallest)',
  'sortFileType': 'File type',

  // Keyboard navigation hint
  'hintNavigate': 'Navigate',
  'hintNextResult': 'Next result',
  'hintNewSearch': 'New search',

  // Empty state
  'emptyTitle': 'No results for “{query}”',
  'emptyBody':
    'Try describing your file differently. DeskSearch understands meaning, so a different phrasing might find what you need.',
  'searchTips': 'Search tips',
  'tip1': 'Try describing what the file is about, e.g. "project budget spreadsheet"',
  'tip2': 'Use natural language like "meeting notes from last month"',
  'tip3': 'Search by content, not filename — e.g. "invoice from Acme Corp"',
  'tip4': 'Broaden your search — remove specific dates or names',
  'newSearch': 'Try a new search',

  // Error state
  'errorTitleServer': "Can't reach DeskSearch",
  'errorTitleGeneric': 'Something went wrong',
  'errorBodyServer': 'Make sure the DeskSearch app is running, then try again.',
  'errorBodyGeneric': 'Try refreshing the page. If this keeps happening, restart DeskSearch.',
  'refreshPage': 'Refresh page',

  // Relevance / match score
  'scoreExcellent': 'Excellent',
  'scoreGood': 'Good',
  'scorePartial': 'Partial',

  // Relative dates
  'daysAgo': '{count}d ago',
  'weeksAgo': '{count}w ago',

  // Result card actions + related documents
  'copied': 'Copied',
  'copyPath': 'Copy path',
  'quickPreview': 'Quick preview',
  'similar': 'Similar',
  'similarTitle': '{filename} ({percent}% similar)',

  // Document preview panel
  'previewUnavailable': 'Preview unavailable',
  'statSize': 'Size',
  'statWords': 'Words',
  'statChunks': 'Chunks',
  'lastModified': 'Last modified:',
  'keyTopics': 'Key Topics',
  'contentPreview': 'Content Preview',
  'closeEsc': 'Close (Esc)',

  // Status bar
  'updatedJustNow': 'Updated just now',
  'updatedMinutesAgo': 'Updated {count}m ago',
  'updatedHoursAgo': 'Updated {count}h ago',
  'updatedOn': 'Updated on {date}',
  'notRunning': "DeskSearch isn't running",
  'notRunningHint': '— Open the DeskSearch app and try again',
  'readingFiles': 'Reading files…',
  'readingYourFiles': 'Reading your files…',
  'filesReady': '{count} files ready',
  'filesReady_one': '{count} file ready',
  'filesReadyLabel': 'files ready',
  'filesReadyLabel_one': 'file ready',
  'doneSoFar': '{count} done so far',
  'doneCount': '{count} done',
  'noFilesIndexed': 'No files indexed yet',
  'noFilesIndexedHint': 'No files indexed yet — add a folder to get started',
} as const;
