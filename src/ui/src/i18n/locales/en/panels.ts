/**
 * panels namespace (en).
 *
 * Flat { key: string } map; the `panels.` prefix is added automatically by
 * locales/index.ts, so components call `t('panels.<sub>.<key>')`.
 *
 * Sub-namespaces:
 *   dashboard.*   Dashboard.tsx
 *   analytics.*   AnalyticsDashboard.tsx
 *   topics.*      TopicsPanel.tsx
 *   duplicates.*  DuplicatesPanel.tsx
 *   sources.*     DataSources.tsx
 *   explorer.*    FileExplorer.tsx
 */
export default {
  // ── Dashboard ──────────────────────────────────────────────────────────────
  'dashboard.totalFiles': 'Total Files',
  'dashboard.indexSize': 'Index Size',
  'dashboard.status': 'Status',
  'dashboard.statusIndexing': 'Indexing…',
  'dashboard.statusReady': 'Ready',
  'dashboard.indexedSegments': 'indexed segments',
  'dashboard.fileTypes': 'File Types',
  'dashboard.noFilesIndexed': 'No files indexed yet',
  'dashboard.addFoldersHint': 'Add folders in the Folders tab',
  'dashboard.watchedFolders': 'Watched Folders',
  'dashboard.noFoldersConfigured': 'No folders configured',
  'dashboard.addFoldersConfiguredHint': 'Go to the Folders tab to add some',
  'dashboard.indexedAgo': 'Indexed {time}',
  'dashboard.recentActivity': 'Recent Indexing Activity',
  'dashboard.noRecentActivity': 'No recent activity',
  'dashboard.failedToLoad': 'Failed to load dashboard data',
  'dashboard.timeAgoJustNow': 'just now',
  'dashboard.timeAgoMinutes': '{count}m ago',
  'dashboard.timeAgoHours': '{count}h ago',
  'dashboard.timeAgoDays': '{count}d ago',

  // ── Analytics ──────────────────────────────────────────────────────────────
  'analytics.title': '📊 Search Insights',
  'analytics.subtitle': 'Understand how you use DeskSearch',
  'analytics.range7': 'Last 7 days',
  'analytics.range30': 'Last 30 days',
  'analytics.range90': 'Last 90 days',
  'analytics.emptyTitle': 'No analytics data yet. Start searching!',
  'analytics.totalSearches': 'Total Searches',
  'analytics.filesAccessed': 'Files Accessed',
  'analytics.inLastDays': 'in the last {count} days',
  'analytics.viaSearchResults': 'via search results',
  'analytics.searchActivity': 'Search Activity',
  'analytics.topSearches': '🔥 Your Most Searched Topics',
  'analytics.mostAccessedFiles': '📂 Most Accessed Files',
  'analytics.noSearchesYet': 'No searches yet',
  'analytics.searchHistoryHint': 'Your search history will appear here',
  'analytics.barTooltip': '{date}: {count} searches',

  // ── Topics ─────────────────────────────────────────────────────────────────
  'topics.title': '🗂 Smart Collections',
  'topics.subtitle': 'Your documents, automatically grouped by topic',
  'topics.topicsLabel': 'Topics:',
  'topics.autoOption': 'Auto',
  'topics.docCount': '{count} documents',
  'topics.docCount_one': '{count} document',
  'topics.refreshClusters': 'Refresh clusters',
  'topics.loadFailed': 'Could not load topics',
  'topics.tryAgain': 'Try again',
  'topics.notEnoughDocuments': 'Not enough documents',
  'topics.notEnoughDocumentsHint': 'Index at least a few documents to see topic groups',
  'topics.summary': '{topics} topics discovered across {docs} documents',
  'topics.summaryTopics': '{count} topics',
  'topics.summaryDocuments': '{count} documents',
  'topics.showMore': '+{count} more files',
  'topics.showLess': 'Show less',
  'topics.footer1': 'Topics are generated from document content using AI clustering.',
  'topics.footer2': 'They update automatically as your index changes.',

  // ── Duplicates ─────────────────────────────────────────────────────────────
  'duplicates.title': '🔁 Duplicate Files',
  'duplicates.subtitle': 'Files with nearly identical content',
  'duplicates.sensitivityLabel': 'Sensitivity:',
  'duplicates.sensitivityVeryStrict': 'Very strict (98%+)',
  'duplicates.sensitivityStrict': 'Strict (95%+)',
  'duplicates.sensitivityNormal': 'Normal (92%+)',
  'duplicates.sensitivityLoose': 'Loose (85%+)',
  'duplicates.rescan': 'Re-scan',
  'duplicates.similarityPercent': '{percent}% similar',
  'duplicates.nearIdentical': '⚠️ Near-identical content',
  'duplicates.verySimilar': 'Very similar content',
  'duplicates.similar': 'Similar content',
  'duplicates.scanFailed': 'Scan failed',
  'duplicates.tryAgain': 'Try again',
  'duplicates.foundPairs': 'Found {count} pairs of similar files',
  'duplicates.foundPairs_one': 'Found {count} pair of similar files',
  'duplicates.foundPairsHint': 'Review them below and delete any unwanted copies',
  'duplicates.noneFound': 'No duplicates found',
  'duplicates.noneFoundHint':
    'All your files have unique content at the {percent}% similarity threshold',
  'duplicates.copyPath': 'Copy path',
  'duplicates.footer1': 'Similarity is based on document content, not filenames.',
  'duplicates.footer2': 'Open both files to compare before deleting.',

  // ── Data sources ───────────────────────────────────────────────────────────
  'sources.title': 'Data Sources',
  'sources.subtitle':
    'Connect external data sources to make them searchable alongside your local files.',
  'sources.infoLead': 'Configure a data source, then click ',
  'sources.infoSyncLabel': 'Sync',
  'sources.infoTail':
    ' to import its content into your search index. You can sync at any time to pull in new data.',
  'sources.configured': 'Configured',
  'sources.sync': 'Sync',
  'sources.syncing': 'Syncing…',
  'sources.noDocumentsFound': 'No documents found. Check the connector configuration.',
  'sources.syncResult': 'Found {found} documents, indexed {indexed}',
  'sources.syncErrors': ', {count} errors',
  'sources.saveConfig': '💾 Save Configuration',
  'sources.noConfigNeeded':
    'This connector works automatically with no configuration needed.',
  'sources.noneAvailable': 'No connectors available.',

  // Data source config fields
  'sources.emailDirsLabel': 'Email directories',
  'sources.emailDirsPlaceholder': '/path/to/emails\n/path/to/mbox-files',
  'sources.emailDirsHelp': 'One directory per line containing .eml or .mbox files',
  'sources.dirsLabel': 'Directories to scan',
  'sources.dirsPlaceholder': '/path/to/documents\n/path/to/notes',
  'sources.dirsHelp': 'One directory per line',
  'sources.extensionsLabel': 'File extensions',
  'sources.extensionsPlaceholder': '.txt, .md, .pdf',
  'sources.extensionsHelp': 'Comma-separated (leave empty for defaults)',
  'sources.maxFileSizeLabel': 'Max file size (MB)',
  'sources.maxFileSizePlaceholder': '50',
  'sources.exportPathLabel': 'Export path',
  'sources.exportPathPlaceholder': '/path/to/slack-export or /path/to/export.zip',
  'sources.exportPathHelp': 'Path to extracted Slack export directory or ZIP file',
  'sources.includeBotsLabel': 'Include bot messages',
  'sources.includeBotsPlaceholder': 'false',
  'sources.includeBotsHelp': 'Set to "true" to include bot messages',
  'sources.chromeBookmarksLabel': 'Chrome bookmarks path',
  'sources.chromeBookmarksPlaceholder': '(auto-detected)',
  'sources.chromeBookmarksHelp': 'Override the default Chrome bookmarks path',
  'sources.firefoxPlacesLabel': 'Firefox places path',
  'sources.firefoxPlacesPlaceholder': '(auto-detected)',
  'sources.firefoxPlacesHelp': 'Override the default Firefox places.sqlite path',

  // ── File explorer ──────────────────────────────────────────────────────────
  'explorer.indexedFiles': 'Indexed Files',
  'explorer.countFiles': '{count} files',
  'explorer.countFiles_one': '{count} file',
  'explorer.searchPlaceholder': 'Search files...',
  'explorer.allTypes': 'All types',
  'explorer.removeSelected': 'Remove {count} selected',
  'explorer.colName': 'Name',
  'explorer.colType': 'Type',
  'explorer.colSize': 'Size',
  'explorer.colModified': 'Modified',
  'explorer.colChunks': 'Chunks',
  'explorer.colIndexed': 'Indexed',
  'explorer.noFilesFound': 'No files found',
  'explorer.noFilesFoundHint': 'Try a different filter or add folders to index',
  'explorer.pageOf': 'Page {page} of {total}',
  'explorer.prev': 'Prev',
  'explorer.next': 'Next',
} as const;
