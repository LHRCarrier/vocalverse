<script setup lang="ts">
/**
 * 审核 · 处置记录（docs/50 §5.3.7「单一审计流」、§9.3 审计纪律、§10.2 `GET /audit-logs`）。
 *
 * 本页是**派生视图**，不是一张自己的表：设计上刻意不建 `moderation_actions`——
 * 决定的前后状态写进 `admin_audit_logs.detail`（`{decision,prevStatus,nextStatus,reasonCode,note}`），
 * `moderation_cases` 只存当前状态。好处是「谁在什么时候把哪条内容怎么了」只有一个答案，
 * 因此本页与「系统 · 审计日志」展示的是**同一批行**，只是视角不同（本页只保留审核域动作）。
 *
 * 口径提醒（必须写在页面上，否则读者会以为是两个数据源）：
 * 本页的「全部审核动作」档在客户端按 `moderation.` 前缀回扫（服务端 `GET /audit-logs` **另有**
 * `actionPrefix` 前缀查询参数可用 —— `AdminAuditLogRepository.search` 里是
 * `a.action like concat(:actionPrefix, '%')`；本页暂未改用它，因此总数是"已扫到的下界"，
 * 页面上的措辞必须与此一致，不能声称服务端不支持前缀查询）。
 */
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NDataTable, NSelect, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

import { consoleApi } from '@/api'
import type { AuditLogRow, PageView } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { usePagedList } from '@/composables/usePagedList'
import { fmtDateTime, fmtInt, fmtRelative } from '@/utils/format'

import {
  AUDIT_RESULT_OPTIONS,
  MODERATION_ACTION_LABEL,
  MODERATION_ACTION_OPTIONS,
  auditDecisionText,
  auditNoteText,
  prettyJson,
} from './moderationMeta'

/** 「全部审核动作」哨兵值：n-select 需要非空 value，故不用空串 */
const ALL_ACTIONS = '__all__'
/** 回扫粒度与上限：审计表是 append-only 大表，不设上限会让一次翻页打出几十个请求 */
const SCAN_PAGE_SIZE = 100
const SCAN_MAX_ROWS = 1000
/** 时间窗上限 92 天，与 `ConsoleAuditController.MAX_WINDOW_DAYS` 对齐（超出服务端回 46007） */
const MAX_WINDOW_DAYS = 92

/** 需要索引签名：`usePagedList` 的筛选泛型约束是 `Record<string, unknown>`（interface 不会隐式获得索引签名） */
type AuditFilters = {
  action: string
  result: string
  from: string
  to: string
}

const message = useMessage()

const scanned = ref(0)
const truncated = ref(false)
const rangeFrom = ref('')
const rangeTo = ref('')

async function fetchLogs(
  q: AuditFilters & { page: number; page_size: number },
): Promise<PageView<AuditLogRow>> {
  scanned.value = 0
  truncated.value = false
  // 具体动作 → 服务端精确匹配：total 与分页都准，还能吃到 ix_admin_audit_logs_action_created
  if (q.action !== ALL_ACTIONS) return consoleApi.listAuditLogs({ ...q, action: q.action })
  return scanModerationLogs(q)
}

/** 前缀档：按页回扫审计流，只留下 `moderation.*` 的行（服务端不支持前缀查询） */
async function scanModerationLogs(
  q: AuditFilters & { page: number; page_size: number },
): Promise<PageView<AuditLogRow>> {
  const need = q.page * q.page_size
  const kept: AuditLogRow[] = []
  let serverPage = 1
  let seen = 0
  let exhausted = false
  while (seen < SCAN_MAX_ROWS) {
    const res = await consoleApi.listAuditLogs({
      page: serverPage,
      page_size: SCAN_PAGE_SIZE,
      result: q.result || undefined,
      from: q.from || undefined,
      to: q.to || undefined,
    })
    seen += res.items.length
    kept.push(...res.items.filter((row) => row.action.startsWith('moderation.')))
    if (res.items.length < SCAN_PAGE_SIZE || serverPage * SCAN_PAGE_SIZE >= res.total) {
      exhausted = true
      break
    }
    if (kept.length >= need) break
    serverPage += 1
  }
  scanned.value = seen
  // 未扫到底 → total 只是下界，列表页要在「共 N 条」后加 `+`，不能假装知道总数
  truncated.value = !exhausted
  return {
    items: kept.slice((q.page - 1) * q.page_size, need),
    total: kept.length,
    page: q.page,
    page_size: q.page_size,
  }
}

const logs = usePagedList<AuditLogRow, AuditFilters>(fetchLogs, {
  action: ALL_ACTIONS,
  result: '',
  from: '',
  to: '',
})

onMounted(() => void logs.load())

/** 回扫口径说明：读者看到「共 N 条+」时必须能立刻知道为什么不是个确切数字 */
const scanNote = computed(() => {
  if (logs.filters.value.action !== ALL_ACTIONS) {
    return '当前按具体动作查询：服务端精确匹配（可用 ix_admin_audit_logs_action_created），总数与分页都是准的。切到「全部审核动作」时改为前端按 moderation. 前缀回扫审计流（服务端的 actionPrefix 前缀查询本页暂未使用）。'
  }
  const tail = truncated.value
    ? ' 行并触达回扫上限，因此「共 N 条」是下界；更早的记录请用动作或时间范围收窄。'
    : ' 行（已扫到审计流末尾，总数为准确值）。'
  return `「全部审核动作」档由前端按 moderation. 前缀回扫（未使用服务端的 actionPrefix 查询），本次已回扫 ${fmtInt(scanned.value)}${tail}`
})

/** `yyyy-MM-dd`（本地时区）→ ISO-8601 with offset，服务端收 `@DateTimeFormat(iso = DATE_TIME)` */
function toIso(dateText: string, endOfDay: boolean): string {
  if (!dateText) return ''
  const parsed = new Date(`${dateText}T${endOfDay ? '23:59:59' : '00:00:00'}`)
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toISOString()
}

/** 时间窗过大时先在前端拦下：让审核员就地收窄，比提交后吃 46007 更好 */
async function applyRange(): Promise<void> {
  const from = toIso(rangeFrom.value, false)
  const to = toIso(rangeTo.value, true)
  if (from && to && (new Date(to).getTime() - new Date(from).getTime()) / 86_400_000 > MAX_WINDOW_DAYS) {
    message.warning(`时间窗上限 ${MAX_WINDOW_DAYS} 天，请收窄范围（超出服务端会回 46007）`)
    return
  }
  await logs.applyFilters({ from, to })
}

async function resetFilters(): Promise<void> {
  rangeFrom.value = ''
  rangeTo.value = ''
  await logs.reset()
}

const columns = computed<DataTableColumns<AuditLogRow>>(() => [
  {
    // 展开行 = detail 原始 JSON（文本插值渲染 <pre>，绝不 v-html，docs/50 §11.4）
    type: 'expand',
    width: 34,
    renderExpand: (row: AuditLogRow) => h('pre', { class: 'ma-json' }, prettyJson(row.detail)),
  },
  {
    title: '时间',
    key: 'createdAt',
    width: 168,
    render: (row) =>
      h('span', { class: 'c-num', title: fmtRelative(row.createdAt) }, fmtDateTime(row.createdAt)),
  },
  {
    title: '审核员',
    key: 'adminUsername',
    width: 124,
    // 审计存的是用户名快照：账号被删也能归因（docs/50 §5.3.7）
    render: (row) =>
      h(
        'span',
        {
          class: 'c-mono',
          title: row.adminUserId === null ? '账号已删除，审计保留用户名快照' : `admin_users.id = ${row.adminUserId}`,
        },
        row.adminUsername,
      ),
  },
  {
    title: '动作',
    key: 'action',
    width: 182,
    render: (row) =>
      h('span', { title: row.summary }, [
        h('span', {}, MODERATION_ACTION_LABEL[row.action] ?? row.action),
        h('span', { class: 'c-mono ma-code' }, row.action),
      ]),
  },
  {
    title: '目标',
    key: 'target',
    width: 148,
    render: (row) =>
      h(
        'span',
        { class: 'c-mono' },
        row.targetType === null ? '—' : `${row.targetType}#${row.targetId ?? '—'}`,
      ),
  },
  {
    title: '决定',
    key: 'decision',
    width: 128,
    // 决定取自 detail.decision（白名单字段）；被拒 / 失败的行没有决定，显示「—」
    render: (row) => h('span', {}, auditDecisionText(row)),
  },
  {
    title: '结果',
    key: 'result',
    width: 116,
    render: (row) =>
      h('span', { class: 'ma-result' }, [
        h(StatusBadge, { kind: 'auditResult', value: row.result }),
        row.errorCode === null ? null : h('span', { class: 'c-mono ma-code' }, String(row.errorCode)),
      ]),
  },
  {
    title: '备注',
    key: 'note',
    minWidth: 180,
    render: (row) => h('span', { class: 'ma-note', title: auditNoteText(row) }, auditNoteText(row)),
  },
  {
    title: 'request-id',
    key: 'requestId',
    width: 176,
    render: (row) => h('span', { class: 'c-mono ma-req', title: row.requestId ?? '' }, row.requestId ?? '—'),
  },
])
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="处置记录"
      desc="审核动作只有一条审计流：本页与「系统 · 审计日志」是同一批 admin_audit_logs 行的两个视角（服务端没有独立的审核动作表，docs/50 §5.3.7）。"
    >
      <template #actions>
        <n-button size="small" quaternary @click="logs.load()">刷新</n-button>
      </template>
    </PageHeader>

    <section class="c-card">
      <div class="c-card-head">
        <div>
          <h2 class="c-card-title">审核域审计行</h2>
          <p class="c-card-sub">
            只显示 action 以 <code>moderation.</code> 开头的行；展开任意一行可看 detail 原始 JSON
            （决定的前后状态与原因码都在里面）
          </p>
        </div>
        <div class="ma-filters">
          <n-select
            v-model:value="logs.filters.value.action"
            class="ma-filter ma-filter--lg"
            size="small"
            :options="[{ label: '全部审核动作', value: ALL_ACTIONS }, ...MODERATION_ACTION_OPTIONS]"
            @update:value="logs.applyFilters({})"
          />
          <n-select
            v-model:value="logs.filters.value.result"
            class="ma-filter"
            size="small"
            :options="[{ label: '全部结果', value: '' }, ...AUDIT_RESULT_OPTIONS]"
            @update:value="logs.applyFilters({})"
          />
          <input v-model="rangeFrom" class="ma-date" type="date" aria-label="起始时间" @change="applyRange">
          <span class="c-weak">至</span>
          <input v-model="rangeTo" class="ma-date" type="date" aria-label="截止时间" @change="applyRange">
          <n-button size="small" quaternary @click="resetFilters">重置</n-button>
        </div>
      </div>

      <AsyncBlock
        :loading="logs.loading.value"
        :error="logs.error.value"
        :error-code="logs.errorCode.value"
        :empty="!logs.items.value.length"
        empty-text="没有符合条件的审核处置记录"
        empty-hint="换个动作或时间范围；队列页做过的决定会立即出现在这里"
        :min-height="200"
      >
        <n-data-table
          :columns="columns"
          :data="logs.items.value"
          :row-key="(row: AuditLogRow) => row.id"
          size="small"
          :bordered="false"
        />
        <div class="ma-pager">
          <span class="c-weak">共 {{ fmtInt(logs.total.value) }}{{ truncated ? '+' : '' }} 条</span>
          <n-button
            size="small"
            quaternary
            :disabled="logs.page.value <= 1"
            @click="logs.goPage(logs.page.value - 1)"
          >
            上一页
          </n-button>
          <span class="c-num">{{ logs.page.value }} / {{ logs.pageCount.value }}</span>
          <n-button
            size="small"
            quaternary
            :disabled="logs.page.value >= logs.pageCount.value"
            @click="logs.goPage(logs.page.value + 1)"
          >
            下一页
          </n-button>
        </div>
        <p class="c-weak ma-scan">{{ scanNote }}</p>
      </AsyncBlock>
    </section>
  </div>
</template>

<style scoped>
.ma-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.ma-filter {
  width: 124px;
}
.ma-filter--lg {
  width: 178px;
}
.ma-date {
  height: 30px;
  border: 1px solid var(--c-border);
  border-radius: var(--c-ctl-radius);
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 12.5px;
  padding: 0 8px;
  font-family: inherit;
}
.ma-code {
  margin-left: 6px;
  color: var(--c-text-3);
}
.ma-result {
  display: inline-flex;
  align-items: center;
}
.ma-note {
  display: block;
  max-width: 100%;
  font-size: 12px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.ma-req {
  color: var(--c-text-2);
}
.ma-json {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--c-ctl-radius);
  background: var(--c-surface-sunken);
  color: var(--c-text-2);
  font-family: var(--vv-font-mono);
  font-size: 11.5px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.ma-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 10px;
  font-size: 12.5px;
}
.ma-scan {
  margin: 8px 0 0;
  font-size: 11.5px;
  line-height: 1.6;
}
</style>
