<script setup lang="ts">
/**
 * 上架流水（docs/50 §10.2：`GET /content/publish-events`，数据派生自 `admin_audit_logs`）。
 *
 * **只读页**：没有任何状态变更入口，因此没有 `PermissionGate`（没有可裁剪的动作）；
 * 访问门槛由路由 meta `content:song:read` 把关，与 nav.ts「任一内容读权限可见」的取向一致。
 *
 * ⚠️ 本页的列按后端**真实字段**重建（2026-09-10）。`ConsoleContentController.publishEvents`
 * 回的是 `{id, action, targetType, targetId, operator, adminUserId, summary, detail, createdAt}`：
 * - **没有** `domain`：内容域由 `action`（`content.{domain}.publish`）推导；
 * - **没有** `prevStatus` / `nextStatus`：只剩 detail 原文，解析见 `publishEventDetail`；
 * - 操作人字段名是 `operator`（v1 写 `adminUsername`，恒为 undefined → 该列一直空白）；
 * - 时间列是 `createdAt`（后端**不返回** `publishedAt`）。
 */
import { computed, h, onMounted, ref } from 'vue'
import { NDataTable, NPagination, NSelect } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

import { consoleApi, publishEventDetail, publishEventDomain } from '@/api'
import type { PublishEventRow, PublishTargetType } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { usePagedList } from '@/composables/usePagedList'
import { fmtDateTime, fmtInt, fmtRelative } from '@/utils/format'

/**
 * 筛选档 → 后端 `targetType` 取值。
 * 权威：`ConsoleContentController.publishEvents` 的 `@Pattern(regexp =
 * "song|listening_material|scenario|book|chapter")` —— 是**下划线**与单数，不是端点路径那种复数。
 */
const TARGET_TYPES: { label: string; value: PublishTargetType }[] = [
  { label: '歌曲', value: 'song' },
  { label: '听力素材', value: 'listening_material' },
  { label: '场景', value: 'scenario' },
  { label: '书籍', value: 'book' },
  { label: '章节', value: 'chapter' },
]

const targetTypeOptions = TARGET_TYPES.map(({ label, value }) => ({ label, value }))

/** 审计里的内容域 code（`PublishService.DOMAIN_*`，单数）→ 中文 */
const DOMAIN_LABEL: Record<string, string> = {
  song: '歌曲',
  listening: '听力素材',
  scenario: '场景',
  book: '书籍',
  chapter: '章节',
}

type Filters = {
  targetType: string
}

const { items, total, page, pageCount, loading, error, errorCode, load, applyFilters, goPage } =
  usePagedList<PublishEventRow, Filters>(
    (q) => consoleApi.publishEvents({ page: q.page, page_size: q.page_size, targetType: targetTypeOf(q.targetType) }),
    { targetType: '' },
  )

const targetType = ref<string | null>(null)

// 同 SongsView：把 usePagedList 的 `{value:T[]}` 包成 computed，模板才能直接当数组用
const rows = computed(() => items.value)

/** 空串 = 不筛（`buildUrl` 会自动丢弃空值）；非空时收窄成联合类型 */
function targetTypeOf(value: string): PublishTargetType | undefined {
  const hit = TARGET_TYPES.find((option) => option.value === value)
  return hit?.value
}

function onTargetType(value: string | null): void {
  targetType.value = value
  void applyFilters({ targetType: value ?? '' })
}

/** 前后状态：只在 detail 里（`applyPublish` 写入），解析不出就如实显示「—」 */
function renderTransition(row: PublishEventRow) {
  const { prevStatus, nextStatus } = publishEventDetail(row)
  return h('div', { class: 'flex items-center gap-2' }, [
    prevStatus
      ? h(StatusBadge, { kind: 'publish', value: prevStatus })
      : h('span', { class: 'c-weak text-12px' }, '—'),
    h('span', { class: 'c-weak' }, '→'),
    nextStatus
      ? h(StatusBadge, { kind: 'publish', value: nextStatus })
      : h('span', { class: 'c-weak text-12px' }, '（明细未回传）'),
  ])
}

const columns = computed<DataTableColumns<PublishEventRow>>(() => [
  {
    title: '时间',
    key: 'createdAt',
    width: 190,
    render: (row) =>
      h('div', [
        h('div', fmtDateTime(row.createdAt)),
        h('div', { class: 'c-weak text-12px' }, fmtRelative(row.createdAt)),
      ]),
  },
  {
    title: '内容域',
    key: 'domain',
    width: 120,
    render: (row) => {
      // 推导不出来时回落到 targetType 的真实取值，而不是编一个域
      const domain = publishEventDomain(row)
      return DOMAIN_LABEL[domain ?? ''] ?? domain ?? row.targetType
    },
  },
  {
    title: '目标',
    key: 'targetId',
    width: 170,
    render: (row) => h('span', { class: 'c-mono' }, `${row.targetType}#${row.targetId}`),
  },
  { title: '变更（前 → 后）', key: 'status', width: 240, render: renderTransition },
  {
    title: '操作人',
    key: 'operator',
    width: 150,
    render: (row) => h('span', { class: 'c-mono' }, row.operator || '—'),
  },
  { title: '摘要', key: 'summary', minWidth: 220, ellipsis: { tooltip: true }, render: (row) => row.summary ?? '—' },
])

onMounted(() => void load())
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="上架流水"
      desc="按时间回放内容域的上架 / 下架记录（派生自审计日志，只读）；用于核对哪次操作改动了哪条内容。"
    />

    <div class="c-card">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <n-select
          :value="targetType"
          class="w-40"
          :options="targetTypeOptions"
          clearable
          placeholder="全部目标类型"
          @update:value="onTargetType"
        />
        <span class="c-weak text-12px">共 {{ fmtInt(total) }} 条</span>
        <span class="c-weak text-12px">流水仅覆盖控制台发起的上下架；App 侧与脚本直改数据库不在其中。</span>
      </div>

      <AsyncBlock
        :loading="loading"
        :error="error"
        :error-code="errorCode"
        :empty="rows.length === 0"
        empty-text="还没有上下架记录"
        empty-hint="去歌曲库 / 书籍页做一次上架或下架，这里就会出现流水"
      >
        <n-data-table
          :columns="columns"
          :data="rows"
          :row-key="(row: PublishEventRow) => row.id"
          :bordered="false"
          :single-line="false"
          :pagination="false"
          size="small"
        />
      </AsyncBlock>

      <div class="flex justify-end mt-4">
        <n-pagination :page="page" :page-count="pageCount" :page-slot="7" @update:page="goPage" />
      </div>
    </div>
  </div>
</template>
