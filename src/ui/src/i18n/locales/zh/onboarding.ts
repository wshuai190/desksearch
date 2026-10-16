/**
 * $n namespace (zh).
 *
 * Flat { key: string } map; the $n. prefix is added automatically by
 * locales/index.ts, so components call `t('onboarding.<key>')`.
 *
 * 覆盖首次运行向导（components/Onboarding.tsx）与索引进度提示条
 * （components/IndexingProgress.tsx）。带 `_one` 后缀的 key 是
 * `params.count === 1` 时使用的单数变体（中文与英文保持同形）。
 */
export default {
  // ── 欢迎步骤 ──────────────────────────────────────────────────────────────
  'welcome.title': '欢迎使用 DeskSearch',
  'welcome.subtitle': '描述你想找的内容，就能找到电脑里的任何文件，不必再猜文件名。',
  'welcome.cta': '开始使用 →',
  'welcome.hint': '大约 2 分钟即可完成设置',

  // ── 欢迎步骤：特性卡片 ────────────────────────────────────────────────────
  'features.conversational.title': '像聊天一样搜索',
  'features.conversational.body': '可以直接问「上季度会议的重点结论是什么？」，不用再靠猜文件名。',
  'features.private.title': '完全私密 —— 数据不会离开你的 Mac',
  'features.private.body': '所有处理都在本机完成：不经过云端，不上传文件，也不共享任何数据。',
  'features.formats.title': '支持 PDF、Word 文档、代码等多种格式',
  'features.formats.body': 'DeskSearch 能读取并理解数十种文件格式。',

  // ── 检测到的文件夹类别 ────────────────────────────────────────────────────
  'category.documents.label': '文档',
  'category.documents.description': '你的主要文档目录',
  'category.developer.label': '代码与项目',
  'category.developer.description': '源代码与项目文件',
  'category.notes.label': '笔记',
  'category.notes.description': '笔记与写作内容',

  // ── 选择文件夹步骤 ────────────────────────────────────────────────────────
  'folders.title': 'DeskSearch 需要认识哪些文件夹？',
  'folders.subtitle': '我们在你的 Mac 上找到了这些文件夹。勾选你想要搜索的文件夹，之后随时可以添加或移除。',
  'folders.empty': '没有检测到常见文件夹。请在下方添加一个文件夹路径。',
  'folders.pathPlaceholder': '输入文件夹路径，例如 ~/Documents',
  'folders.addAnotherPlaceholder': '添加其他文件夹路径…',
  'folders.clearSelection': '取消选择',
  'folders.selectAtLeastOne': '请至少选择一个文件夹',
  'folders.startIndexing': '开始为 {count} 个文件夹建立索引 →',
  'folders.startIndexing_one': '开始为 {count} 个文件夹建立索引 →',

  // ── 建立索引步骤 ──────────────────────────────────────────────────────────
  'indexing.title': '正在读取你的文件…',
  'indexing.body': 'DeskSearch 正在了解文件里的内容，以便回答你的问题。这通常需要几分钟。',
  'indexing.filesProcessed': '个文件已处理',
  'indexing.tipLabel': '提示：',
  'indexing.tipBody': '不必在这里等待 —— 建立索引的同时就可以开始搜索。处理的文件越多，搜索结果越准确。',
  'indexing.startSearching': '我现在就开始搜索 →',

  // ── 完成步骤 ──────────────────────────────────────────────────────────────
  'done.title': '一切就绪！',
  'done.count': '{files} 个文件',
  'done.count_one': '{files} 个文件',
  'done.bodyRest': '现在都可以搜索了。用日常的说法描述你想找的内容即可。',
  'done.trySearching': '试试搜索这些内容…',
  'done.example.meeting': '上周的会议记录',
  'done.example.budget': '项目预算表格',
  'done.example.proposal': '关于客户提案的笔记',
  'done.startSearching': '开始搜索 →',

  // ── 索引进度提示条（IndexingProgress.tsx） ────────────────────────────────
  'progress.gettingStarted': '正在启动…',
  'progress.failed': '索引失败 —— {message}',
  'progress.unknownError': '未知错误',
  'progress.completeSummary': '已索引 {files} 个文件，用时 {time}（{rate} 个文件/秒）',
  'progress.completeSummary_one': '已索引 {files} 个文件，用时 {time}（{rate} 个文件/秒）',
  'progress.filesOfTotal': '{processed} / {total} 个文件',
  'progress.foundFiles': '发现 {files} 个文件',
  'progress.foundFiles_one': '发现 {files} 个文件',
  'progress.filesPerSec': '{rate} 个文件/秒',
  'progress.errorCount': '{count} 个错误',
  'progress.errorCount_one': '{count} 个错误',
  'progress.elapsedSeconds': '{seconds} 秒',
  'progress.elapsedMinutesSeconds': '{minutes} 分 {seconds} 秒',
  'progress.phase.discovery': '正在发现文件',
  'progress.phase.parsing': '正在读取文件',
  'progress.phase.embedding': '正在生成向量',
  'progress.phase.storing': '正在写入索引',
  'progress.phase.processing': '处理中',
} as const;
