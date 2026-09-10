/**
 * 题库的列定义（`GET /content/questions`）。
 *
 * 权威：Java `ConsoleContentController.QuestionRow(id, examRevision, itemIndex, kind, prompt,
 * status, updatedAt)`。
 *
 * 与其它三个内容域的**结构性差异**：题库**没有** `content:question:publish` 权限码，
 * `status` 的取值域也只有 `published|archived`（没有 `draft`）—— 题目是"启用 / 归档"两态，
 * 不是三态的上下架语义。所以这里**不挂** `publishActionColumn`（挂上去会得到一个
 * 永远 46002 的按钮：权限码在 `PermissionCatalog` 里根本不存在）。
 */
import { h } from 'vue'
import type { DataTableColumns } from 'naive-ui'

import type { QuestionRow } from '@/api'
import { fmtInt } from '@/utils/format'
import { authoringColumn } from './authoringColumn'
import QuestionArchiveButton from './QuestionArchiveButton.vue'
import { publishStatusColumn, publishUpdatedAtColumn } from './publishColumns'

/** 题型 code → 中文（`QuestionUpsert.kind` 的取值域只有两个） */
const KIND_LABEL: Record<string, string> = { read: '朗读题', qa: '问答题' }

export interface QuestionColumnsOptions {
  /** 打开编辑弹窗（`row = null` 表示新建） */
  onEdit: (row: QuestionRow | null) => void
  /** 归档成功后刷新列表 */
  onChanged: () => void
}

export function questionColumns(opts: QuestionColumnsOptions): DataTableColumns<QuestionRow> {
  return [
    {
      title: '试卷版本',
      key: 'examRevision',
      width: 110,
      render: (row) => h('span', { class: 'c-num' }, row.examRevision === null ? '—' : `第 ${fmtInt(row.examRevision)} 卷`),
    },
    {
      title: '题号',
      key: 'itemIndex',
      width: 90,
      render: (row) => h('span', { class: 'c-num' }, row.itemIndex === null ? '—' : fmtInt(row.itemIndex)),
    },
    {
      title: '题型',
      key: 'kind',
      width: 110,
      render: (row) => (row.kind ? (KIND_LABEL[row.kind] ?? row.kind) : '—'),
    },
    { title: '题干', key: 'prompt', minWidth: 320, ellipsis: { tooltip: true } },
    publishStatusColumn<QuestionRow>(),
    publishUpdatedAtColumn<QuestionRow>(),
    authoringColumn<QuestionRow>('content:question:write', [
      { label: '编辑', onClick: (row) => opts.onEdit(row) },
    ]),
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (row) => h(QuestionArchiveButton, { row, onDone: opts.onChanged }),
    },
  ]
}
