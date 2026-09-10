/**
 * 歌曲库的列定义（`GET /content/songs`）。
 *
 * 权威：Java `ConsoleContentController.SongRow(id, title, artist, level, audioUrl,
 * status, pitchRefStatus, updatedAt)` —— 注意字段是**扁平**的，v1 那个 `meta` 字符串不存在。
 */
import { h } from 'vue'
import { NButton } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import type { TableBaseColumn } from 'naive-ui/es/data-table/src/interface'

import type { SongRow } from '@/api'
import PermissionGate from '@/components/common/PermissionGate.vue'
import { fmtInt } from '@/utils/format'
import {
  publishActionColumn,
  publishStatusColumn,
  publishUpdatedAtColumn,
  type PublishColumnsOptions,
} from './publishColumns'

/**
 * 参考旋律状态 → 徽标文案（`SongEntity.pitchRefStatus`：missing|building|ready|invalid）。
 *
 * 为什么单列一列：`PublishService.validateSong` 把它作为**上架前置校验**（必须 `ready`），
 * 所以它就是"这首歌能不能上架"的可视化预检 —— 不显示的话运营只能点了才知道。
 */
const PITCH_REF: Record<string, { text: string; tone: string }> = {
  ready: { text: '旋律已就绪', tone: 'ok' },
  missing: { text: '无参考旋律', tone: 'warn' },
  building: { text: '生成中', tone: 'info' },
  invalid: { text: '旋律无效', tone: 'danger' },
}

export interface SongColumnsOptions extends PublishColumnsOptions {
  /** 打开歌曲编辑弹窗（`row = null` 表示新建） */
  onEdit: (row: SongRow | null) => void
  /** 打开歌词编辑器 */
  onEditLrc: (row: SongRow) => void
}

/**
 * 内容维护列：编辑歌曲 / 编辑歌词。
 *
 * 为什么与「操作」列分开而不是塞进 `publishActionColumn`：两列是**不同的权限与不同的风险**——
 * 上下架是 `content:song:publish`（状态机动作，必填原因、留审计），编辑是 `content:song:write`
 * （改内容字段）。合成一列会让"这个按钮要不要填原因"变成看着按钮猜。
 */
function authoringColumn(opts: SongColumnsOptions): TableBaseColumn<SongRow> {
  return {
    title: '内容维护',
    key: 'authoring',
    width: 140,
    render: (row) =>
      h(PermissionGate, { code: 'content:song:write' }, () => [
        h(
          NButton,
          { size: 'small', quaternary: true, onClick: () => opts.onEdit(row) },
          () => '编辑',
        ),
        h(
          NButton,
          { size: 'small', quaternary: true, onClick: () => opts.onEditLrc(row) },
          () => '歌词',
        ),
      ]),
  }
}

export function songColumns(opts: SongColumnsOptions): DataTableColumns<SongRow> {
  return [
    {
      title: '歌曲 / 歌手',
      key: 'title',
      minWidth: 240,
      ellipsis: { tooltip: true },
      render: (row) =>
        h('div', [
          h('div', row.title),
          // artist 可为 null（`SongRow.artist` 是 String）——缺就显示「—」，不拼空串
          h('div', { class: 'c-weak text-12px' }, row.artist || '—'),
        ]),
    },
    {
      title: '难度 / 等级',
      key: 'level',
      width: 120,
      // level 可为 null：显示「—」而不是 0（0 是错误信息）
      render: (row) => h('span', { class: 'c-num' }, row.level === null ? '—' : fmtInt(row.level)),
    },
    {
      title: '参考旋律',
      key: 'pitchRefStatus',
      width: 130,
      render: (row) => {
        const meta = PITCH_REF[row.pitchRefStatus ?? ''] ?? {
          text: row.pitchRefStatus ?? '—',
          tone: 'muted',
        }
        return h('span', { class: `c-badge c-badge--${meta.tone}` }, meta.text)
      },
    },
    publishStatusColumn<SongRow>(),
    publishUpdatedAtColumn<SongRow>(),
    authoringColumn(opts),
    publishActionColumn<SongRow>(opts, (row) => row.title),
  ]
}
