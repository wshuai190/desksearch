/**
 * $n namespace (en).
 *
 * Flat { key: string } map; the $n. prefix is added automatically by
 * locales/index.ts, so components call `t('onboarding.<key>')`.
 *
 * Covers the first-run wizard (components/Onboarding.tsx) and the indexing
 * progress banner (components/IndexingProgress.tsx).
 * Keys ending in `_one` are the singular variants used by the engine when
 * `params.count === 1`.
 */
export default {
  // ── Welcome step ──────────────────────────────────────────────────────────
  'welcome.title': 'Welcome to DeskSearch',
  'welcome.subtitle':
    "Find anything on your computer — by describing what you're looking for, not just the filename.",
  'welcome.cta': 'Get started →',
  'welcome.hint': 'Takes about 2 minutes to set up',

  // ── Welcome step: feature cards ───────────────────────────────────────────
  'features.conversational.title': "Search like you're talking to someone",
  'features.conversational.body':
    'Ask "what were the key takeaways from the Q3 meeting?" instead of guessing filenames.',
  'features.private.title': 'Completely private — nothing leaves your Mac',
  'features.private.body':
    'All processing happens on your computer. No cloud, no uploads, no data sharing.',
  'features.formats.title': 'Works on PDFs, Word docs, code, and more',
  'features.formats.body': 'DeskSearch reads and understands dozens of file formats.',

  // ── Detected folder categories ────────────────────────────────────────────
  'category.documents.label': 'Documents',
  'category.documents.description': 'Your main document storage',
  'category.developer.label': 'Code & Projects',
  'category.developer.description': 'Source code and project files',
  'category.notes.label': 'Notes',
  'category.notes.description': 'Notes and writing',

  // ── Folder selection step ─────────────────────────────────────────────────
  'folders.title': 'Which folders should DeskSearch know about?',
  'folders.subtitle':
    "We found these folders on your Mac. Check the ones you'd like to be able to search. You can always add or remove folders later.",
  'folders.empty': 'No common folders detected. Add a folder path below to get started.',
  'folders.pathPlaceholder': 'Enter folder path, e.g. ~/Documents',
  'folders.addAnotherPlaceholder': 'Add another folder path…',
  'folders.clearSelection': 'Clear selection',
  'folders.selectAtLeastOne': 'Select at least one folder',
  'folders.startIndexing': 'Start indexing {count} folders →',
  'folders.startIndexing_one': 'Start indexing {count} folder →',

  // ── Indexing step ─────────────────────────────────────────────────────────
  'indexing.title': 'Reading your files…',
  'indexing.body':
    "DeskSearch is learning what's in your files so it can answer your questions. This usually takes a few minutes.",
  'indexing.filesProcessed': 'files processed',
  'indexing.tipLabel': 'Tip:',
  'indexing.tipBody':
    "You don't have to wait here — you can start searching as files are indexed. Searches will get better as more files are processed.",
  'indexing.startSearching': "I'll start searching now →",

  // ── Done step ─────────────────────────────────────────────────────────────
  'done.title': "You're all set!",
  'done.count': '{files} files',
  'done.count_one': '{files} file',
  'done.bodyRest':
    "are now searchable. Just describe what you're looking for in plain English.",
  'done.trySearching': 'Try searching for…',
  'done.example.meeting': 'meeting notes from last week',
  'done.example.budget': 'project budget spreadsheet',
  'done.example.proposal': 'notes about the client proposal',
  'done.startSearching': 'Start searching →',

  // ── Indexing progress banner (IndexingProgress.tsx) ───────────────────────
  'progress.gettingStarted': 'Getting started…',
  'progress.failed': 'Indexing failed — {message}',
  'progress.unknownError': 'Unknown error',
  'progress.completeSummary': 'Indexed {files} files in {time} ({rate} files/sec)',
  'progress.completeSummary_one': 'Indexed {files} file in {time} ({rate} files/sec)',
  'progress.filesOfTotal': '{processed} / {total} files',
  'progress.foundFiles': 'Found {files} files',
  'progress.foundFiles_one': 'Found {files} file',
  'progress.filesPerSec': '{rate} files/sec',
  'progress.errorCount': '{count} errors',
  'progress.errorCount_one': '{count} error',
  'progress.elapsedSeconds': '{seconds}s',
  'progress.elapsedMinutesSeconds': '{minutes}m {seconds}s',
  'progress.phase.discovery': 'Discovering files',
  'progress.phase.parsing': 'Reading files',
  'progress.phase.embedding': 'Generating embeddings',
  'progress.phase.storing': 'Saving to index',
  'progress.phase.processing': 'Processing',
} as const;
