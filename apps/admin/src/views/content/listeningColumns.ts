/**
 * 听力素材的列定义（`GET /content/listening-materials`）。
 *
 * 权威：Java `ConsoleContentController.MaterialRow(id, title, level, audioUrl,
 * hasTranscript, status, updatedAt)` —— `hasTranscript` 是服务端算好的**布尔位**
 * （`e.getTranscript() != null && !e.getTranscript().isBlank()`），前端拿不到原文，
 * 也不该假设它有内容；同样**没有** `meta` 字段。
 */
import { h } from 'vue'
import type { DataTableColumns } from 'naive-ui'

import type { MaterialRow } from '@/api'
import { fmtInt } from '@/utils/format'
import { authoringColumn } from './authoringColumn'
import {
  publishActionColumn,
  publishStatusColumn,
  publishUpdatedAtColumn,
  type PublishColumnsOptions,
} from './publishColumns'

export interface MaterialColumnsOptions extends PublishColumnsOptions {
  /** 打开编辑弹窗（`row = null` 表示新建） */
  onEdit: (row: MaterialRow | null) => void
}

export function materialColumns(opts: MaterialColumnsOptions): DataTableColumns<MaterialRow> {
  return [
    { title: '标题', key: 'title', minWidth: 240, ellipsis: { tooltip: true } },
    {
      title: '难度 / 等级',
      key: 'level',
      width: 120,
      // level 可为 null：显示「—」而不是 0
      render: (row) => h('span', { class: 'c-num' }, row.level === null ? '—' : fmtInt(row.level)),
    },
    {
      title: '文本（transcript）',
      key: 'hasTranscript',
      width: 150,
      // 上架前置校验要求 transcript 非空（`PublishService.validateMaterial`），故这列就是预检
      render: (row) =>
        row.hasTranscript
          ? h('span', { class: 'c-badge c-badge--ok' }, '已填写')
          : h('span', { class: 'c-badge c-badge--warn' }, '缺文本'),
    },
    publishStatusColumn<MaterialRow>(),
    publishUpdatedAtColumn<MaterialRow>(),
    authoringColumn<MaterialRow>('content:listening:write', [
      { label: '编辑', onClick: (row) => opts.onEdit(row) },
    ]),
    publishActionColumn<MaterialRow>(opts, (row) => row.title),
  ]
}
