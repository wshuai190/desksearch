/**
 * `settings` 命名空间（中文）—— 设置页、手机访问卡片与文件夹管理。
 *
 * 这里是扁平的 { key: string } 映射，`settings.` 前缀由 locales/index.ts
 * 自动添加，因此组件里写 `t('settings.<key>')`。
 * 通用词请复用 `common.ts`，例如 `t('common.save')`。
 */
export default {
  // 页面标题
  'title': '设置',
  'subtitle': '配置 DeskSearch 如何索引和检索你的文件。',

  // 状态提示
  'saved': '设置已保存！请重新索引文件夹，改动才会生效。',
  'saveFailed': '保存失败，请重试。',
  'connectionError': '连接 DeskSearch 失败，请确认应用正在运行。',
  'loadFailed': '设置加载失败，请确认 DeskSearch 正在运行。',

  // 通用
  'general.title': '通用',
  'general.description': 'DeskSearch 实例的基础配置',
  'general.embeddingModel': '嵌入模型',
  'general.embeddingModelDescription': '由 Starbucks 2D Matryoshka 嵌入模型驱动 —— 该模型有论文支撑，支持灵活的分层 × 维度截断（ECIR 2026）',
  'general.storageLocation': '存储位置',
  'general.storageLocationDescription': 'DeskSearch 存放索引的位置',
  'general.serverAddress': '服务器地址',
  'general.serverAddressDescription': 'DeskSearch 监听的网络地址',
  'general.languageDescription': '选择界面的显示语言',

  // 索引
  'indexing.title': '索引',
  'indexing.description': '控制 DeskSearch 处理哪些文件，以及如何处理',
  'indexing.strategy': '索引策略',
  'indexing.strategyDescription': '选择 DeskSearch 切分文件的方式，以便快速检索',
  'indexing.fileTypes': '文件类型',
  'indexing.fileTypesDescription': '选择要加入索引的文件类型',
  'indexing.additionalTypes': '其他文件类型',
  'indexing.additionalTypesPlaceholder': '例如 .rs、.toml、.r',
  'indexing.separateWithCommas': '用逗号分隔',

  // 索引速度档位
  'speed.fast.title': '快速',
  'speed.fast.description': '片段更小，索引更快',
  'speed.balanced.title': '均衡',
  'speed.balanced.description': '适合大多数使用场景',
  'speed.thorough.title': '精细',
  'speed.thorough.description': '片段更大，上下文更完整',
  'speed.recommended': '推荐',
  'speed.meta': '{chars} 字符 · 重叠 {overlap}',

  // 文件类型名称
  'types.pdfs': 'PDF 文件',
  'types.word': 'Word 文档',
  'types.text': '文本文件',
  'types.markdown': '笔记（Markdown）',
  'types.spreadsheets': '电子表格',
  'types.csv': 'CSV 数据',
  'types.python': 'Python 脚本',
  'types.notebooks': 'Jupyter 笔记本',
  'types.emails': '电子邮件',
  'types.web': '网页',

  // 检索
  'search.description': '微调检索行为与文件大小限制',
  'search.maxFileSize': '最大文件大小',
  'search.maxFileSizeDescription': '索引时会跳过大于此值的文件',
  'search.excludedFolders': '排除的文件夹',
  'search.excludedFoldersDescription': '要跳过的文件夹名（例如 .git、node_modules）',

  // 保存区域
  'footer.hint': '改动需要重新索引后才会生效。',
  'saveButton': '保存设置',

  // 手机访问
  'mobile.title': '手机访问',
  'mobile.description': '在手机上检索你的文件',
  'mobile.qrAlt': '在手机上打开 DeskSearch 的二维码',
  'mobile.scanHint': '用手机相机扫描二维码',
  'mobile.sameWifi': '手机需要连接到同一个 Wi-Fi 网络。',
  'mobile.copyUrl': '复制链接',
  'mobile.localhostPrefix': '你正在通过 ',
  'mobile.localhostSuffix': ' 访问 DeskSearch。要在手机上使用：',
  'mobile.step1Prefix': '请确保手机连接到',
  'mobile.step1Strong': '同一 Wi-Fi',
  'mobile.step2': '找到电脑的 IP 地址（通常是 192.168…）',
  'mobile.step3Prefix': '打开：',

  // 文件夹管理
  'folders.title': '你的检索文件夹',
  'folders.subtitle': 'DeskSearch 会索引这些文件夹中的文件，方便你进行检索。',
  'folders.addTitle': '添加文件夹',
  'folders.pathPlaceholder': '输入文件夹路径，或点击「浏览」…',
  'folders.browse': '浏览',
  'folders.addButton': '添加文件夹',
  'folders.adding': '添加中…',
  'folders.addFailed': '添加文件夹失败，请确认该路径存在。',
  'folders.empty.title': '还没有添加文件夹',
  'folders.empty.hint1': '点击',
  'folders.empty.hint2': '从电脑中选择文件夹，或在上方输入路径后点击',
  'folders.empty.hint3': '。',
  'folders.empty.suggestions': '可以从这些位置开始：文档、桌面、下载',
  'folders.advanced.show': '显示高级选项',
  'folders.advanced.hide': '隐藏高级选项',
  'folders.advanced.hint': '这些选项很少需要用到，只有在检索结果看起来过时或不对时才使用。',
  'folders.advanced.clearAll': '🗑️  清除全部检索数据并重新开始',
  'folders.clearing': '正在清除…',
  'folders.confirmClearIndex': '这会删除以下位置的检索索引：\n\n{path}\n\n文件夹会保留在列表中，随时可以重新索引。',
  'folders.confirmClearAll': '这会清空整个检索索引，之后需要重新索引各个文件夹。\n\n文件夹列表会保留。是否继续？',

  // 文件夹浏览弹窗
  'folders.browser.title': '选择文件夹',
  'folders.browser.goUp': '返回上级',
  'folders.browser.empty': '这里没有子文件夹',
  'folders.browser.addThisFolder': '添加此文件夹',

  // 索引进度
  'folders.progress.start': '正在准备…',
  'folders.progress.discovery': '正在查找要索引的文件…',
  'folders.progress.scanning': '正在扫描…',
  'folders.progress.readingFile': '正在读取「{filename}」',
  'folders.progress.reading': '正在读取文件…',
  'folders.progress.understandingFile': '正在理解「{filename}」',
  'folders.progress.processing': '正在处理文件…',
  'folders.progress.processingFile': '正在处理「{filename}」',
  'folders.progress.storing': '正在保存索引…',

  // 文件夹卡片
  'folders.fileCount': '{n} 个文件可检索',
  'folders.fileCount_one': '{n} 个文件可检索',
  'folders.noFilesIndexed': '尚未索引任何文件',
  'folders.updated': '更新于 {time}',
  'folders.minutesAgo': '{count} 分钟前',
  'folders.minutesAgo_one': '{count} 分钟前',
  'folders.hoursAgo': '{count} 小时前',
  'folders.hoursAgo_one': '{count} 小时前',
  'folders.daysAgo': '{count} 天前',
  'folders.daysAgo_one': '{count} 天前',
  'folders.watching': '正在监控变更',
  'folders.reindexTitle': '重新扫描此文件夹，以收录新增和修改的文件',
  'folders.refreshing': '刷新中…',
  'folders.refreshFiles': '刷新文件',
  'folders.clearIndexTitle': '仅删除此文件夹的索引',
  'folders.clearIndex': '清除索引',
  'folders.removeTitle': '将此文件夹从 DeskSearch 中移除',
  'folders.removing': '移除中…',
} as const;
