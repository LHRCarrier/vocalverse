<script setup lang="ts">
/**
 * 审计日志（docs/50 §9.3 内容纪律 / §10.2 `GET /audit-logs`）。
 *
 * 三条口径：
 * 1. **只读页**，没有任何状态变更入口，因此没有 `PermissionGate`——访问门槛由路由 meta
 *    `console:audit:read` 把关（`admin_audit_logs` 是 append-only，界面本就不该提供改写入口）；
 * 2. `detail` 用文本插值渲染成 JSON（`<pre>{{ }}</pre>`），**绝不 v-html**（§11.4 XSS 红线）；
 * 3. `detail` 是服务端按字段白名单（§9.3 `FIELD_ALLOWLIST`）裁剪后的结果——白名单外的键会被
 *    静默丢弃，所以"detail 里没有某个字段"不等于"这次操作没有该字段"，页面要把它说清楚。
 */
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NDataTable, NDatePicker, NInput, NPagination, NSelect } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

import { consoleApi } from '@/api'
import type { AuditLogRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { debounce } from '@/composables/useAsync'
import { usePagedList } from '@/composables/usePagedList'
import { fmtDateTime, fmtInt, fmtRelative } from '@/utils/format'

type Filters = {
  action: string
  targetType: string
  result: string
  from: string
  to: string
}

const { items, total, page, pageCount, loading, error, errorCode, load, applyFilters, goPage } =
  usePagedList<AuditLogRow, Filters>((q) => consoleApi.listAuditLogs(q), {
    action: '',
    targetType: '',
    result: '',
    from: '',
    to: '',
  })

const action = ref('')
const targetType = ref('')
const result = ref<string | null>(null)
const range = ref<[number, number] | null>(null)

// usePagedList 的 items 被标成 `{value:T[]}`，模板不会把它当 Ref 解包，故包一层 computed
const rows = computed(() => items.value)

const debouncedAction = debounce((value: string) => void applyFilters({ action: value.trim() }), 350)
const debouncedTarget = debounce((value: string) => void applyFilters({ targetType: value.trim() }), 350)

function onAction(value: string): void {
  action.value = value
  debouncedAction(value)
}

function onTargetType(value: string): void {
  targetType.value = value
  debouncedTarget(value)
}

function onResult(value: string | null): void {
  result.value = value
  void applyFilters({ result: value ?? '' })
}

/** 时间范围 → ISO-8601（docs/50 §10.1：请求时间一律带 offset；toISOString 的 Z 合法） */
function onRange(value: [number, number] | null): void {
  range.value = value
  if (!value) {
    void applyFilters({ from: '', to: '' })
    return
  }
  void applyFilters({ from: new Date(value[0]).toISOString(), to: new Date(value[1]).toISOString() })
}

function resetFilters(): void {
  action.value = ''
  targetType.value = ''
  result.value = null
  range.value = null
  void applyFilters({ action: '', targetType: '', result: '', from: '', to: '' })
}

/**
 * detail 的展示：白名单裁剪后可能为空。
 * 空 detail 有两种来源——该动作本就没有可记字段、或字段被 §9.3 白名单拦下——都要给出去向，
 * 否则排查的人会以为前端把数据吞了。
 */
function stringifyDetail(detail: Record<string, unknown> | null): string {
  if (!detail || Object.keys(detail).length === 0) {
    return '（无 detail：该动作没有可下发字段，或字段被 docs/50 §9.3 的 FIELD_ALLOWLIST 拦下并计数）'
  }
  try {
    return JSON.stringify(detail, null, 2)
  } catch {
    return '（detail 无法序列化）'
  }
}

/** 目标列：`targetType` + `targetId`（`AuditLogView` 给的是**字符串** targetId，媒体用 public_id） */
function targetText(row: AuditLogRow): string {
  return row.targetType ? `${row.targetType}#${row.targetId ?? '—'}` : '—'
}

const columns = computed<DataTableColumns<AuditLogRow>>(() => [
  { type: 'expand', renderExpand: (row) => renderDetail(row) },
  {
    title: '时间',
    key: 'createdAt',
    width: 180,
    render: (row) =>
      h('div', [
        h('div', fmtDateTime(row.createdAt)),
        h('div', { class: 'c-weak text-12px' }, fmtRelative(row.createdAt)),
      ]),
  },
  { title: '操作人', key: 'adminUsername', width: 130, render: (row) => h('span', { class: 'c-mono' }, row.adminUsername) },
  { title: '动作', key: 'action', width: 200, render: (row) => h('span', { class: 'c-mono' }, row.action) },
  {
    title: '目标',
    key: 'targetType',
    width: 180,
    render: (row) => h('span', { class: 'c-mono' }, targetText(row)),
  },
  {
    title: '结果',
    key: 'result',
    width: 100,
    render: (row) => h(StatusBadge, { kind: 'auditResult', value: row.result }),
  },
  { title: '摘要', key: 'summary', minWidth: 220, ellipsis: { tooltip: true } },
  {
    title: 'request-id',
    key: 'requestId',
    width: 220,
    render: (row) => h('span', { class: 'c-mono c-weak', title: row.requestId ?? '' }, row.requestId ?? '—'),
  },
])

/**
 * 展开区：把审计里"不进主表但排查要用"的字段 + detail JSON 一次给全。
 *
 * ⚠️ 不再显示「耗时」：`AdminAuditLogEntity` 有 `duration_ms` 列，但
 * `ConsoleAuditController.AuditLogView` **没有把它放进对外 record**（`toView` 只映射 13 个字段），
 * 前端读 `row.durationMs` 只会拿到 undefined —— 与其显示「耗时 —」，不如不显示这一项。
 */
function renderDetail(row: AuditLogRow) {
  return h('div', { class: 'p-2' }, [
    h('div', { class: 'flex flex-wrap gap-4 mb-2 c-muted text-12px' }, [
      h('span', `来源 IP ${row.ip ?? '—'}`),
      h('span', `错误码 ${row.errorCode ?? '—'}`),
      h('span', `管理员 id ${row.adminUserId ?? '—'}`),
      h('span', `记录 id ${row.id}`),
    ]),
    h(
      'pre',
      {
        class: 'c-mono m-0 p-2 whitespace-pre-wrap break-all',
        style: 'background: var(--c-surface-sunken); border-radius: var(--c-ctl-radius)',
      },
      stringifyDetail(row.detail),
    ),
  ])
}

onMounted(() => void load())
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="审计日志"
      desc="控制台所有写动作与登录事件的留痕（append-only）；展开行看 detail 明细与 request-id 便于对日志。"
    />

    <div class="c-card">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <n-input
          :value="action"
          class="w-56"
          clearable
          placeholder="动作，如 content.songs.publish"
          @update:value="onAction"
        />
        <n-input
          :value="targetType"
          class="w-44"
          clearable
          placeholder="目标类型，如 song / admin_user"
          @update:value="onTargetType"
        />
        <n-select
          :value="result"
          class="w-32"
          :options="[
            { label: '成功', value: 'ok' },
            { label: '被拒', value: 'denied' },
            { label: '失败', value: 'failed' },
          ]"
          clearable
          placeholder="全部结果"
          @update:value="onResult"
        />
        <n-date-picker
          :value="range"
          type="datetimerange"
          clearable
          class="w-90"
          @update:value="onRange"
        />
        <n-button quaternary size="small" @click="resetFilters">重置筛选</n-button>
        <span class="c-weak text-12px">共 {{ fmtInt(total) }} 条</span>
      </div>

      <AsyncBlock
        :loading="loading"
        :error="error"
        :error-code="errorCode"
        :empty="rows.length === 0"
        empty-text="没有匹配的审计记录"
        empty-hint="放宽筛选条件或清空时间范围再试"
      >
        <n-data-table
          :columns="columns"
          :data="rows"
          :row-key="(row: AuditLogRow) => row.id"
          :bordered="false"
          :single-line="false"
          :pagination="false"
          :scroll-x="1400"
          size="small"
        />
      </AsyncBlock>

      <div class="flex justify-end mt-4">
        <n-pagination :page="page" :page-count="pageCount" :page-slot="7" @update:page="goPage" />
      </div>
    </div>
  </div>
</template>
