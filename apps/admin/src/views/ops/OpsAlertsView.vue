<script setup lang="ts">
/**
 * 运维 · 预警中心（docs/50 §6.3）。
 *
 * 设计要点：
 * - **预警不是闹钟**：同规则同窗口只出一条（服务端 `dedup_key` 去抖）；
 *   恢复**不自动 resolve**，必须人工确认——否则抖动型指标会刷屏把真事件埋掉。
 * - 规则在这里可改阈值与开关；改了写审计（谁把告警关掉的必须查得到）。
 */
import { computed, h, onMounted } from 'vue'
import { NButton, NDataTable, NInputNumber, NSwitch, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

import { ApiError, opsApi } from '@/api'
import type { AlertEvent, AlertRule } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import PermissionGate from '@/components/common/PermissionGate.vue'
import StatTile from '@/components/common/StatTile.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { useAsync, useRealtimeRefresh } from '@/composables/useAsync'
import { usePagedList } from '@/composables/usePagedList'
import { fmtDateTime, fmtInt, fmtRelative } from '@/utils/format'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const message = useMessage()

const rules = useAsync(() => opsApi.listRules())
const events = usePagedList<AlertEvent, { status: string; severity: string }>(
  (q) => opsApi.listEvents(q),
  { status: 'firing', severity: '' },
)

onMounted(() => {
  void rules.run()
  void events.load()
})
useRealtimeRefresh(() => void events.load(), 30_000)

const canWrite = computed(() => auth.hasPermission('ops:alert:write'))
/** 规则列表出参是 `{items}`（ops.py:278），不是裸数组 */
const ruleRows = computed(() => rules.state.value.data?.items ?? [])
const firing = computed(() => events.items.value.filter((e) => e.status === 'firing').length)
const critical = computed(
  () => events.items.value.filter((e) => e.status === 'firing' && e.severity === 'critical').length,
)
const enabledRules = computed(() => ruleRows.value.filter((r) => r.enabled).length)

function report(err: unknown, okText: string): void {
  const e = err as ApiError
  if (e.code === 46002) message.warning(`权限不足：需要 ${(e.data as { required?: string })?.required ?? 'ops:alert:write'}`)
  else message.error(e.message)
  void okText
}

async function act(fn: () => Promise<unknown>, okText: string): Promise<void> {
  try {
    await fn()
    message.success(okText)
    await events.load()
  } catch (err) {
    report(err, okText)
  }
}

async function toggleRule(rule: AlertRule, enabled: boolean): Promise<void> {
  try {
    await opsApi.updateRule(rule.id, { enabled })
    message.success(enabled ? `已启用「${rule.name}」` : `已停用「${rule.name}」`)
    await rules.run()
  } catch (err) {
    report(err, '')
    await rules.run()
  }
}

async function saveThreshold(rule: AlertRule, threshold: number | null): Promise<void> {
  if (threshold === null || threshold === rule.threshold) return
  try {
    await opsApi.updateRule(rule.id, { threshold })
    message.success(`「${rule.name}」阈值已更新为 ${threshold}`)
    await rules.run()
  } catch (err) {
    report(err, '')
    await rules.run()
  }
}

const eventColumns = computed<DataTableColumns<AlertEvent>>(() => [
  {
    title: '严重级',
    key: 'severity',
    width: 92,
    render: (row) => h(StatusBadge, { kind: 'severity', value: row.severity }),
  },
  {
    title: '规则',
    key: 'rule_code',
    width: 190,
    render: (row) => h('span', { class: 'c-mono' }, row.rule_code),
  },
  { title: '说明', key: 'message', minWidth: 240, ellipsis: { tooltip: true } },
  {
    title: '触发值',
    key: 'value',
    width: 120,
    render: (row) =>
      h('span', { class: 'c-num' }, `${row.value} / 阈值 ${row.threshold}`),
  },
  {
    title: '状态',
    key: 'status',
    width: 96,
    render: (row) => h(StatusBadge, { kind: 'alertStatus', value: row.status }),
  },
  {
    title: '触发时间',
    key: 'fired_at',
    width: 170,
    render: (row) => h('span', { title: fmtDateTime(row.fired_at) }, fmtRelative(row.fired_at)),
  },
  {
    title: '操作',
    key: 'actions',
    width: 168,
    render: (row) => {
      if (!canWrite.value || row.status === 'resolved') return h('span', { class: 'c-weak' }, '—')
      const buttons = [
        row.status === 'firing'
          ? h(
              NButton,
              {
                size: 'small',
                quaternary: true,
                // ack 端点不收请求体（ops.py:398-404），acked_by 由服务端写用户名快照
                onClick: () => void act(() => opsApi.ackEvent(row.id), '已确认'),
              },
              { default: () => '确认' },
            )
          : null,
        h(
          NButton,
          {
            size: 'small',
            quaternary: true,
            type: 'primary',
            onClick: () => void act(() => opsApi.resolveEvent(row.id, '控制台标记恢复'), '已标记恢复'),
          },
          { default: () => '标记恢复' },
        ),
      ]
      return h('span', { class: 'oa-actions' }, buttons)
    },
  },
])

const COMPARATOR_SYMBOL: Record<AlertRule['comparator'], string> = {
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
}

const ruleColumns = computed<DataTableColumns<AlertRule>>(() => [
  { title: '规则', key: 'name', minWidth: 180, ellipsis: { tooltip: true } },
  { title: '指标', key: 'metric', width: 240, render: (row) => h('span', { class: 'c-mono' }, row.metric) },
  {
    title: '条件',
    key: 'condition',
    width: 96,
    render: (row) => h('span', { class: 'c-num' }, COMPARATOR_SYMBOL[row.comparator]),
  },
  {
    title: '阈值',
    key: 'threshold',
    width: 150,
    render: (row) =>
      h(NInputNumber, {
        value: row.threshold,
        size: 'small',
        disabled: !canWrite.value,
        min: 0,
        style: 'width:120px',
        'onUpdate:value': (v: number | null) => void saveThreshold(row, v),
      }),
  },
  {
    title: '窗口',
    key: 'window_s',
    width: 92,
    render: (row) => h('span', { class: 'c-num' }, `${row.window_s}s`),
  },
  {
    title: '最少样本桶',
    key: 'min_samples',
    width: 104,
    render: (row) => h('span', { class: 'c-num', title: '窗口内样本桶数少于此值不判定（防冷启动误报）' }, String(row.min_samples)),
  },
  {
    title: '冷却',
    key: 'cooldown_s',
    width: 88,
    render: (row) => h('span', { class: 'c-num' }, `${row.cooldown_s}s`),
  },
  {
    title: '严重级',
    key: 'severity',
    width: 92,
    render: (row) => h(StatusBadge, { kind: 'severity', value: row.severity }),
  },
  {
    title: '启用',
    key: 'enabled',
    width: 88,
    render: (row) =>
      h(NSwitch, {
        value: row.enabled,
        size: 'small',
        disabled: !canWrite.value,
        'onUpdate:value': (v: boolean) => void toggleRule(row, v),
      }),
  },
])
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="预警中心"
      desc="同规则同窗口只出一条；恢复不自动关闭，必须人工标记 —— 抖动型指标不该刷屏把真事件埋掉。"
    >
      <template #actions>
        <span v-if="!canWrite" class="c-badge c-badge--muted">只读（需 ops:alert:write）</span>
      </template>
    </PageHeader>

    <div class="c-stat-row" style="margin-bottom: 14px">
      <StatTile label="未处理" :value="fmtInt(firing)" unit="条" :tone="firing > 0 ? 'danger' : 'ok'" hint="status = firing" />
      <StatTile label="其中严重" :value="fmtInt(critical)" unit="条" :tone="critical > 0 ? 'danger' : undefined" />
      <StatTile label="启用中的规则" :value="fmtInt(enabledRules)" unit="条" :hint="`共 ${ruleRows.length} 条规则`" />
    </div>

    <section class="c-card">
      <div class="c-card-head">
        <div>
          <h2 class="c-card-title">预警事件</h2>
          <p class="c-card-sub">按触发时间倒序 · 冷却期内同规则不重复出条</p>
        </div>
        <div class="oa-filters">
          <select v-model="events.filters.value.status" class="oa-select" @change="events.applyFilters({})">
            <option value="">全部状态</option>
            <option value="firing">未处理</option>
            <option value="acknowledged">已确认</option>
            <option value="resolved">已恢复</option>
          </select>
          <select v-model="events.filters.value.severity" class="oa-select" @change="events.applyFilters({})">
            <option value="">全部级别</option>
            <option value="critical">严重</option>
            <option value="warn">警告</option>
            <option value="info">提示</option>
          </select>
        </div>
      </div>

      <AsyncBlock
        :loading="events.loading.value"
        :error="events.error.value"
        :error-code="events.errorCode.value"
        :empty="!events.items.value.length"
        empty-text="没有符合条件的预警"
        :min-height="160"
      >
        <n-data-table
          :columns="eventColumns"
          :data="events.items.value"
          :row-key="(row: AlertEvent) => row.id"
          size="small"
          :bordered="false"
        />
        <div class="oa-pager">
          <span class="c-weak">共 {{ fmtInt(events.total.value) }} 条</span>
          <n-button
            size="small"
            quaternary
            :disabled="events.page.value <= 1"
            @click="events.goPage(events.page.value - 1)"
          >
            上一页
          </n-button>
          <span class="c-num">{{ events.page.value }} / {{ events.pageCount.value }}</span>
          <n-button
            size="small"
            quaternary
            :disabled="events.page.value >= events.pageCount.value"
            @click="events.goPage(events.page.value + 1)"
          >
            下一页
          </n-button>
        </div>
      </AsyncBlock>
    </section>

    <section class="c-card" style="margin-top: 14px">
      <div class="c-card-head">
        <div>
          <h2 class="c-card-title">规则配置</h2>
          <p class="c-card-sub">
            阈值改动立即生效并写审计；关掉一条规则等于关掉一条防线，请写清原因后再关
          </p>
        </div>
      </div>
      <PermissionGate code="ops:alert:write">
        <template #disabled>
          <p class="c-weak" style="font-size: 12.5px; margin: 0 0 10px">
            当前账号只读。需要 <code>ops:alert:write</code> 才能修改阈值与开关。
          </p>
        </template>
      </PermissionGate>

      <AsyncBlock
        :loading="rules.state.value.loading"
        :error="rules.state.value.error"
        :error-code="rules.state.value.errorCode"
        :empty="!ruleRows.length"
        empty-text="还没有配置任何预警规则"
        :min-height="140"
      >
        <n-data-table
          :columns="ruleColumns"
          :data="ruleRows"
          :row-key="(row: AlertRule) => row.id"
          size="small"
          :bordered="false"
        />
      </AsyncBlock>
    </section>
  </div>
</template>

<style scoped>
.oa-filters {
  display: flex;
  gap: 6px;
}
.oa-select {
  height: 30px;
  border: 1px solid var(--c-border);
  border-radius: var(--c-ctl-radius);
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 12.5px;
  padding: 0 8px;
  font-family: inherit;
}
.oa-actions {
  display: inline-flex;
  gap: 2px;
}
.oa-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 10px;
  font-size: 12.5px;
}
</style>
