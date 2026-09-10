/**
 * 待审队列的列定义（从 `QueueView.vue` 抽出：页面本体要留在 ESLint `max-lines` 之下，
 * 而"行怎么渲染"是纯映射，与页面状态无关——抽出来后页面只剩编排，改动半径也小）。
 *
 * 两个显示口径在这里统一：
 * - 用户内容（`snippet`）一律文本插值 + 单行省略 + 原生 `title` 提示，**绝不 v-html**（docs/50 §11.4）；
 * - 终态单不再给处置按钮（服务端会回 46010），改显示"谁、何时处理的"。
 */
import { h } from 'vue'
import { NButton } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import type { VNodeChild } from 'vue'

import type { ModerationCaseRow } from '@/api'
import PermissionGate from '@/components/common/PermissionGate.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { fmtDateTime, fmtRelative } from '@/utils/format'

import {
  PRIORITY_LABEL,
  PRIORITY_TONE,
  SOURCE_LABEL,
  TARGET_TYPE_LABEL,
  assigneeText,
  deciderText,
  isTerminalCase,
  reasonCodeText,
  reportCountText,
} from './moderationMeta'

export interface QueueColumnHandlers {
  /** 当前管理员 id（认领人列显示「我」用） */
  meId: () => number | null
  canDecide: () => boolean
  assign: (row: ModerationCaseRow) => void
  decide: (row: ModerationCaseRow) => void
}

function rowActions(row: ModerationCaseRow, handlers: QueueColumnHandlers): VNodeChild {
  if (!handlers.canDecide()) return h('span', { class: 'c-weak' }, '只读')
  if (isTerminalCase(row)) {
    return h(
      'span',
      { class: 'c-weak' },
      `${deciderText(row, handlers.meId())} · ${fmtDateTime(row.decidedAt)}`,
    )
  }
  const mine = handlers.meId() !== null && row.assigneeId === handlers.meId()
  const buttons = [
    h(
      NButton,
      { size: 'tiny', quaternary: true, onClick: () => handlers.assign(row) },
      { default: () => (mine ? '取消认领' : '认领') },
    ),
    h(
      NButton,
      { size: 'tiny', quaternary: true, type: 'primary', onClick: () => handlers.decide(row) },
      { default: () => '决定' },
    ),
  ]
  // 认领与决定都是写操作（服务端两条端点都要求 moderation:decide）→ 统一过权限门（docs/50 §4.3）
  return h(
    PermissionGate,
    { code: 'moderation:decide' },
    { default: () => h('span', { class: 'mq-actions' }, buttons) },
  )
}

export function buildQueueColumns(handlers: QueueColumnHandlers): DataTableColumns<ModerationCaseRow> {
  return [
    {
      title: '目标',
      key: 'target',
      width: 128,
      render: (row) =>
        h('span', {}, [
          h('span', { class: 'c-muted' }, TARGET_TYPE_LABEL[row.targetType] ?? row.targetType),
          h('span', { class: 'c-mono mq-target-id' }, `#${row.targetId}`),
        ]),
    },
    {
      title: '来源',
      key: 'source',
      width: 76,
      render: (row) => h('span', {}, SOURCE_LABEL[row.source] ?? row.source),
    },
    {
      title: '原因码',
      key: 'reasonCode',
      width: 108,
      render: (row) => h('span', { title: row.reasonCode }, reasonCodeText(row.reasonCode)),
    },
    {
      title: '优先级',
      key: 'priority',
      width: 80,
      render: (row) =>
        h(
          'span',
          { class: `c-badge c-badge--${PRIORITY_TONE[row.priority] ?? 'muted'}` },
          PRIORITY_LABEL[row.priority] ?? String(row.priority),
        ),
    },
    {
      title: '状态',
      key: 'status',
      width: 92,
      render: (row) => h(StatusBadge, { kind: 'moderation', value: row.status }),
    },
    {
      title: '内容摘要',
      key: 'snippet',
      minWidth: 220,
      render: (row) => h('span', { class: 'mq-snippet', title: row.snippet ?? '' }, row.snippet || '—'),
    },
    {
      title: '举报数',
      key: 'reportCount',
      width: 78,
      render: (row) => h('span', { class: 'c-num' }, reportCountText(row)),
    },
    {
      title: '认领人',
      key: 'assignee',
      width: 112,
      render: (row) =>
        h(
          'span',
          { class: row.assigneeId === null ? 'c-weak' : '' },
          assigneeText(row, handlers.meId()),
        ),
    },
    {
      title: '建单时间',
      key: 'createdAt',
      width: 168,
      render: (row) =>
        h('span', { class: 'c-num', title: fmtRelative(row.createdAt) }, fmtDateTime(row.createdAt)),
    },
    { title: '操作', key: 'actions', width: 190, render: (row) => rowActions(row, handlers) },
  ]
}
