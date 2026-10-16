/**
 * `settings` namespace (en) — Settings page, mobile access card and folder manager.
 *
 * Flat { key: string } map; the `settings.` prefix is added automatically by
 * locales/index.ts, so components call `t('settings.<key>')`.
 * Generic words live in `common.ts` — use `t('common.save')` for those.
 */
export default {
  // Page header
  'title': 'Settings',
  'subtitle': 'Configure how DeskSearch indexes and searches your files.',

  // Status messages
  'saved': 'Settings saved! Re-index your folders for changes to take effect.',
  'saveFailed': 'Couldn\'t save — please try again.',
  'connectionError': 'Couldn\'t connect to DeskSearch. Is the app running?',
  'loadFailed': 'Couldn\'t load settings. Make sure DeskSearch is running.',

  // Section: General
  'general.title': 'General',
  'general.description': 'Basic configuration for your DeskSearch instance',
  'general.embeddingModel': 'Embedding Model',
  'general.embeddingModelDescription': 'Powered by Starbucks 2D Matryoshka embeddings — a research-backed model enabling flexible layer × dimension truncation (ECIR 2026)',
  'general.storageLocation': 'Storage Location',
  'general.storageLocationDescription': 'Where DeskSearch keeps its index',
  'general.serverAddress': 'Server Address',
  'general.serverAddressDescription': 'Network address DeskSearch listens on',
  'general.languageDescription': 'Choose the language used across the interface',

  // Section: Indexing
  'indexing.title': 'Indexing',
  'indexing.description': 'Control what and how DeskSearch processes your files',
  'indexing.strategy': 'Indexing Strategy',
  'indexing.strategyDescription': 'Choose how DeskSearch splits your files for searching',
  'indexing.fileTypes': 'File Types',
  'indexing.fileTypesDescription': 'Select which file types to include in the index',
  'indexing.additionalTypes': 'Additional file types',
  'indexing.additionalTypesPlaceholder': 'e.g. .rs, .toml, .r',
  'indexing.separateWithCommas': 'Separate with commas',

  // Indexing speed tiers
  'speed.fast.title': 'Fast',
  'speed.fast.description': 'Smaller chunks, quicker indexing',
  'speed.balanced.title': 'Balanced',
  'speed.balanced.description': 'Best for most use cases',
  'speed.thorough.title': 'Thorough',
  'speed.thorough.description': 'Larger chunks, better context',
  'speed.recommended': 'Recommended',
  'speed.meta': '{chars} chars · {overlap} overlap',

  // File type labels
  'types.pdfs': 'PDFs',
  'types.word': 'Word documents',
  'types.text': 'Text files',
  'types.markdown': 'Notes (Markdown)',
  'types.spreadsheets': 'Spreadsheets',
  'types.csv': 'CSV data',
  'types.python': 'Python scripts',
  'types.notebooks': 'Notebooks',
  'types.emails': 'Emails',
  'types.web': 'Web pages',

  // Section: Search
  'search.description': 'Fine-tune search behavior and file limits',
  'search.maxFileSize': 'Max File Size',
  'search.maxFileSizeDescription': 'Files larger than this are skipped during indexing',
  'search.excludedFolders': 'Excluded Folders',
  'search.excludedFoldersDescription': 'Folder names to skip (e.g. .git, node_modules)',

  // Save area
  'footer.hint': 'Changes require re-indexing to take effect.',
  'saveButton': 'Save Settings',

  // Mobile access
  'mobile.title': 'Mobile Access',
  'mobile.description': 'Search your files from your phone',
  'mobile.qrAlt': 'QR code to open DeskSearch on your phone',
  'mobile.scanHint': 'Scan with your phone\'s camera',
  'mobile.sameWifi': 'Your phone needs to be on the same Wi-Fi network.',
  'mobile.copyUrl': 'Copy URL',
  'mobile.localhostPrefix': 'You\'re accessing DeskSearch from ',
  'mobile.localhostSuffix': '. To use on your phone:',
  'mobile.step1Prefix': 'Make sure your phone is on the ',
  'mobile.step1Strong': 'same Wi-Fi',
  'mobile.step2': 'Find your computer\'s IP (usually 192.168…)',
  'mobile.step3Prefix': 'Open: ',

  // Folder manager
  'folders.title': 'Your Search Folders',
  'folders.subtitle': 'DeskSearch will index files in these folders so you can search them.',
  'folders.addTitle': 'Add a folder',
  'folders.pathPlaceholder': 'Type a folder path, or click Browse…',
  'folders.browse': 'Browse',
  'folders.addButton': 'Add Folder',
  'folders.adding': 'Adding…',
  'folders.addFailed': 'Couldn\'t add that folder — make sure the path exists.',
  'folders.empty.title': 'No folders added yet',
  'folders.empty.hint1': 'Click ',
  'folders.empty.hint2': ' to pick a folder from your computer, or type a path above and click ',
  'folders.empty.hint3': '.',
  'folders.empty.suggestions': 'Good places to start: Documents, Desktop, Downloads',
  'folders.advanced.show': 'Show advanced options',
  'folders.advanced.hide': 'Hide advanced options',
  'folders.advanced.hint': 'These options are rarely needed. Use them only if your search results seem outdated or wrong.',
  'folders.advanced.clearAll': '🗑️  Clear all search data and start over',
  'folders.clearing': 'Clearing…',
  'folders.confirmClearIndex': 'This will remove the search index for:\n\n{path}\n\nThe folder stays in your list and can be re-indexed anytime.',
  'folders.confirmClearAll': 'This will clear the entire search index and you\'ll need to re-index your folders.\n\nYour folder list will stay. Continue?',

  // Folder browser modal
  'folders.browser.title': 'Choose a Folder',
  'folders.browser.goUp': 'Go up',
  'folders.browser.empty': 'No subfolders here',
  'folders.browser.addThisFolder': 'Add This Folder',

  // Indexing progress
  'folders.progress.start': 'Getting started…',
  'folders.progress.discovery': 'Finding files to index…',
  'folders.progress.scanning': 'Scanning…',
  'folders.progress.readingFile': 'Reading "{filename}"',
  'folders.progress.reading': 'Reading files…',
  'folders.progress.understandingFile': 'Understanding "{filename}"',
  'folders.progress.processing': 'Processing files…',
  'folders.progress.processingFile': 'Processing "{filename}"',
  'folders.progress.storing': 'Saving index…',

  // Folder card
  'folders.fileCount': '{n} files searchable',
  'folders.fileCount_one': '{n} file searchable',
  'folders.noFilesIndexed': 'No files indexed yet',
  'folders.updated': 'Updated {time}',
  'folders.minutesAgo': '{count} minutes ago',
  'folders.minutesAgo_one': '{count} minute ago',
  'folders.hoursAgo': '{count} hours ago',
  'folders.hoursAgo_one': '{count} hour ago',
  'folders.daysAgo': '{count} days ago',
  'folders.daysAgo_one': '{count} day ago',
  'folders.watching': 'Watching for changes',
  'folders.reindexTitle': 'Re-scan this folder to pick up new and changed files',
  'folders.refreshing': 'Refreshing…',
  'folders.refreshFiles': 'Refresh files',
  'folders.clearIndexTitle': 'Remove the index for this folder only',
  'folders.clearIndex': 'Clear index',
  'folders.removeTitle': 'Remove this folder from DeskSearch',
  'folders.removing': 'Removing…',
} as const;
