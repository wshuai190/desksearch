/**
 * `filters` namespace (zh)。
 *
 * 扁平 { key: string } 映射；`filters.` 前缀由 locales/index.ts 自动添加，
 * 因此组件里写 `t('filters.<key>')`。
 */
export default {
  // 面板
  'title': '筛选',

  // 文件类型
  'fileType': '文件类型',
  'type.pdf': 'PDF',
  'type.txt': '文本',
  'type.md': 'Markdown',
  'type.docx': 'Word',
  'type.xlsx': 'Excel',
  'type.csv': 'CSV',
  'type.py': 'Python',
  'type.js': 'JavaScript',
  'type.ts': 'TypeScript',
  'type.html': 'HTML',
  'type.json': 'JSON',
  'type.eml': '邮件',
  'type.ipynb': '笔记本',

  // 时间范围
  'dateRange': '时间范围',
  'from': '起始日期',
  'to': '结束日期',

  // 文件夹
  'folder': '文件夹',
  'allFolders': '全部文件夹',
  'folderPlaceholder': '例如 ~/Documents',

  // AI 回答横幅
  'answer.title': 'AI 回答',
  'answer.extracted': '摘自你的文档',
  'answer.copy': '复制回答',
  'answer.scrollHint': '向下滚动查看来源文档',
} as const;
