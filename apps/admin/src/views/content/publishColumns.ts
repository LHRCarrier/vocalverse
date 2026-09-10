/**
 * 内容上下架列表的**公共列**（歌曲 / 听力素材 / 场景 / 题库四个域共用）。
 *
 * 抽取口径（2026-09-10 重写）：v1 的 `contentColumns` 假设四个域同构、都读一个 `meta` 字段，
 * 但 Java `ConsoleContentController` 返回的是**四个不同 record**，且**没有** `meta`
 * —— 于是「元数据」列恒为空。四个域真正共有的只有 `id` / `status` / `updatedAt` / 上下架动作，
 * 所以这里只抽这四列，各域的差异列由**各自的列定义文件**提供（`songsColumns.ts` 等）。
 * 这样每个域的字段与文案在同一个文件里逐条对齐 Java record，不存在"猜一个 meta 字符串"的中间层。
 */
import { h } from 'vue'
import type { TableBaseColumn } from 'naive-ui/es/data-table/src/interface'

import type { ContentRowBase, PublishDomain } from '@/api'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { fmtDateTime, fmtRelative } from '@/utils/format'
import PublishActionButton from './PublishActionButton.vue'

export interface PublishColumnsOptions {
  /** 上下架动作的域 code（`PublishService.DOMAIN_*`：song / listening / scenario） */
  domain: PublishDomain
  /** 该域专属的上下架权限码（docs/50 §4.2：每个域一个 publish 码） */
  publishPermission: string
  /** 下架无用户侧消费者时在确认框里重复提示（docs/50 §15.2 G-2） */
  consumerNote?: string
  /** 状态变更成功后刷新列表 */
  onChanged: () => void
}

/** 状态列：publish 徽标的语义（draft/published/archived）见 `StatusBadge` */
export function publishStatusColumn<T extends ContentRowBase>(): TableBaseColumn<T> {
  return {
    title: '状态',
    key: 'status',
    width: 110,
    render: (row) => h(StatusBadge, { kind: 'publish', value: String(row.status) }),
  }
}

/** 更新时间列：绝对时间 + 相对时间两行（控制台所有内容页统一口径） */
export function publishUpdatedAtColumn<T extends ContentRowBase>(): TableBaseColumn<T> {
  return {
    title: '更新时间',
    key: 'updatedAt',
    width: 180,
    render: (row) =>
      h('div', [
        h('div', fmtDateTime(row.updatedAt)),
        h('div', { class: 'c-weak text-12px' }, fmtRelative(row.updatedAt)),
      ]),
  }
}

/** 操作列：上下架按钮（按钮自带 `PermissionGate`，见 `PublishActionButton`） */
export function publishActionColumn<T extends ContentRowBase>(
  opts: PublishColumnsOptions,
  titleOf: (row: T) => string,
): TableBaseColumn<T> {
  return {
    title: '操作',
    key: 'actions',
    width: 120,
    render: (row) =>
      h(PublishActionButton, {
        domain: opts.domain,
        id: row.id,
        title: titleOf(row),
        status: String(row.status),
        permission: opts.publishPermission,
        consumerNote: opts.consumerNote,
        onDone: opts.onChanged,
      }),
  }
}
