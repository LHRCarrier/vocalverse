/**
 * 场景库的列定义（`GET /content/scenarios`）。
 *
 * 权威：Java `ConsoleContentController.ScenarioRow(id, title, sceneType, difficulty,
 * status, corpusItemCount, updatedAt)`。`corpusItemCount` 是服务端按
 * `PublishService.countCorpusItems`（`English|中文` 逐行计数，与 Python 解析同口径）算出来的，
 * 而上架前置校验要求 ≥3 —— 所以这一列直接就是那次 46011 的可视化预检。
 */
import { h } from 'vue'
import type { DataTableColumns } from 'naive-ui'

import type { ScenarioRow } from '@/api'
import { fmtInt } from '@/utils/format'
import { authoringColumn } from './authoringColumn'
import {
  publishActionColumn,
  publishStatusColumn,
  publishUpdatedAtColumn,
  type PublishColumnsOptions,
} from './publishColumns'

/** 上架门槛（`PublishService.validateScenario`：目标语料 ≥3 条） */
const MIN_CORPUS_ITEMS = 3

export interface ScenarioColumnsOptions extends PublishColumnsOptions {
  /** 打开编辑弹窗（`row = null` 表示新建） */
  onEdit: (row: ScenarioRow | null) => void
}

export function scenarioColumns(opts: ScenarioColumnsOptions): DataTableColumns<ScenarioRow> {
  return [
    { title: '场景标题', key: 'title', minWidth: 220, ellipsis: { tooltip: true } },
    {
      title: '场景类型',
      key: 'sceneType',
      width: 140,
      render: (row) => row.sceneType || '—',
    },
    {
      title: '难度',
      key: 'difficulty',
      width: 90,
      render: (row) => h('span', { class: 'c-num' }, row.difficulty === null ? '—' : fmtInt(row.difficulty)),
    },
    {
      title: '语言点（目标语料）',
      key: 'corpusItemCount',
      width: 160,
      render: (row) => {
        const enough = row.corpusItemCount >= MIN_CORPUS_ITEMS
        return h('div', { class: 'flex items-center gap-2' }, [
          h('span', { class: 'c-num' }, `${fmtInt(row.corpusItemCount)} 条`),
          h(
            'span',
            { class: enough ? 'c-weak text-12px' : 'text-12px', style: enough ? undefined : 'color: var(--c-warn)' },
            enough ? '满足上架门槛' : `少于 ${MIN_CORPUS_ITEMS} 条，上架会被拦`,
          ),
        ])
      },
    },
    publishStatusColumn<ScenarioRow>(),
    publishUpdatedAtColumn<ScenarioRow>(),
    authoringColumn<ScenarioRow>('content:scenario:write', [
      { label: '编辑', onClick: (row) => opts.onEdit(row) },
    ]),
    publishActionColumn<ScenarioRow>(opts, (row) => row.title),
  ]
}
