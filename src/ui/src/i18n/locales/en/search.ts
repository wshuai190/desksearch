/**
 * `search` namespace (en) — search bar, hero, quick stats, tips, examples.
 */
export default {
  // Input
  'placeholder': 'Search your files...',
  'placeholderListening': 'Listening…',
  'voiceSearch': 'Search by voice',
  'voiceUnsupported': 'Voice search is not supported in this browser.',
  'clearTitle': 'Clear (Esc)',
  'clearLabel': 'Clear search',
  'recentSearches': 'Recent searches',
  'removeRecent': 'Remove',

  // Hero
  'subtitleCount': 'Search {count} files by meaning',
  'subtitleGeneric': 'Search your files by meaning, not just keywords',
  'indexing': 'Reading your files... you can already start searching!',
  'noFilesTitle': 'No files indexed yet',
  'noFilesHint': 'Go to the {tab} tab and add a folder to get started.',
  'trySearching': 'Try searching for',
  'kbdHintBefore': 'Press',
  'kbdHintOr': 'or',
  'kbdHintAfter': 'to focus anytime',

  // Quick stats
  'stats.filesIndexed': 'Files indexed',
  'stats.lastUpdated': 'Last updated',
  'stats.indexSize': 'Index size',
  'time.never': 'Never',
  'time.justNow': 'Just now',
  'time.minutesAgo': '{count}m ago',
  'time.hoursAgo': '{count}h ago',

  // Tips
  'tips.meaning': 'Search by meaning, not just keywords',
  'tips.filters': 'Filter by date, file type, or folder',
  'tips.voice': 'Use voice search or press / to focus',

  // Rotating example queries (picked 3 at a time)
  'examples.0': 'meeting notes from last month',
  'examples.1': 'project budget spreadsheet',
  'examples.2': 'invoice from Acme Corp',
  'examples.3': 'Python script for data processing',
  'examples.4': 'notes about quarterly review',
  'examples.5': 'contract signed in 2023',
  'examples.6': 'email about the conference',
  'examples.7': 'todo list for the project',
} as const;
