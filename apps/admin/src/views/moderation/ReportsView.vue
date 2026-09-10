<script setup lang="ts">
/**
 * 审核 · 举报处理（docs/50 §5.3.9、§6.2、§10.2）。
 *
 * 举报与审核单是**上下游**关系：举报本身不改动内容，它的终点是审核单——
 * `accept`（受理）会建立或复用该目标的审核单并回填 `case_id`，之后隐藏/删除/驳回都在审核单上做。
 * 因此本页的三个动作对内容都是"零写入"，页面上要写清楚，免得审核员以为「受理 = 已处理」。
 *
 * 跳转口径：没有 per-case 路由，所以「跳到该单」= `router.push('/moderation/queue?caseId=N')`，
 * 待审队列页读到该查询参数会取出该单直接打开决定弹窗（不新造路由，也不假装有详情页）。
 */
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NDataTable, NInput, NSelect, useDialog, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import type { VNodeChild } from 'vue'
import { useRouter } from 'vue-router'

import { ERR, consoleApi } from '@/api'
import type { ModerationReportRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import PermissionGate from '@/components/common/PermissionGate.vue'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { fmtDateTime, fmtInt, fmtRelative } from '@/utils/format'

import {
  REPORT_STATUS_META,
  REPORT_STATUS_OPTIONS,
  TARGET_TYPE_LABEL,
  describeFailure,
  failureLines,
  reasonCodeText,
} from './moderationMeta'

type HandleAction = 'accept' | 'reject' | 'duplicate'

const router = useRouter()
const auth = useAuthStore()
const message = useMessage()
const dialog = useDialog()

const reports = usePagedList<ModerationReportRow, { status: string }>(
  (q) => consoleApi.listReports({ page: q.page, page_size: q.page_size, status: q.status || undefined }),
  { status: 'pending' },
)

const canHandle = computed(() => auth.hasPermission('moderation:report:handle'))

onMounted(() => void reports.load())

/** 三个动作对内容都是零写入，弹窗里必须说清"接下来会发生什么"（docs/50 §6.2 / §5.3.9） */
const ACTION_META: Record<HandleAction, { label: string; title: string; effect: string }> = {
  accept: {
    label: '受理',
    title: '确认受理该举报？',
    effect:
      '受理会建立或复用该目标的审核单并把本举报关联过去（举报状态 → 已受理）。内容此时**不改动**：是否隐藏/删除由审核单上的决定负责。',
  },
  reject: {
    label: '不成立',
    title: '确认判定该举报不成立？',
    effect: '举报关闭为「不成立」，不建审核单、不改动内容（等同于对内容的"通过"）。',
  },
  duplicate: {
    label: '判重',
    title: '确认判定该举报为重复举报？',
    effect: '举报关闭为「重复举报」，不建新审核单、不改动内容；用于同一目标已有在处理中的举报或审核单的情况。',
  },
}

function goQueue(caseId: number | null): void {
  void router.push({
    path: '/moderation/queue',
    query: caseId === null ? {} : { caseId: String(caseId) },
  })
}

/**
 * ⚠️ 契约缺口：`consoleApi.handleReport` 的入参类型写的是 `{decision, note}`，
 * 而 Java `ModerationController.ReportHandle` 收的是 `{action, caseId, note}`（`action` 还是 `@NotNull`）。
 * 只发 `decision` 会被校验拒绝。这里两个键一起发（服务端读 `action`），并把这层缺口记在此处；
 * 修正 `src/api/console.ts` 不在本次改动范围内。
 */
async function callHandle(
  id: number,
  action: HandleAction,
  note: string,
): Promise<ModerationReportRow> {
  const body = { decision: action, action, note: note.trim() || undefined }
  return consoleApi.handleReport(id, body as unknown as { decision: HandleAction; note?: string })
}

function handleFailure(err: unknown): void {
  const failure = describeFailure(err)
  if (failure.code === ERR.REPORT_ALREADY_PENDING) {
    // 46015：同举报人对同目标已有待处理举报（幂等，服务端回传既有 caseId，docs/50 §10.4）
    const suffix = failure.caseId === null ? '（未回传 caseId，请在列表里看「关联审核单」列）' : ` #${failure.caseId}`
    message.warning(`已有一条待处理举报，已跳到既有审核单${suffix}`)
    if (failure.caseId !== null) goQueue(failure.caseId)
    void reports.load()
    return
  }
  if (failure.code === ERR.CASE_STATE_CONFLICT) {
    // 与审核单的 46010 同源：举报已不是 pending，条件 UPDATE 影响 0 行——预期内的并发结果
    message.warning('该举报已被其他人处理，请刷新')
    void reports.load()
    return
  }
  message.error(failureLines(failure).join('；'))
}

/** 确认框正文：举报原文（文本插值）+ 必看的后果说明 + 备注输入（备注进审计 detail.note） */
function dialogBody(row: ModerationReportRow, action: HandleAction, note: { value: string }): VNodeChild {
  const meta = ACTION_META[action]
  return h('div', [
    h('p', { class: 'm-0 c-muted' }, meta.effect),
    h(
      'p',
      { class: 'm-0 mt-2 text-12px', style: 'color: var(--c-text-2)' },
      `目标：${TARGET_TYPE_LABEL[row.targetType] ?? row.targetType} #${row.targetId}　原因码：${reasonCodeText(row.reasonCode)}　举报人：用户 #${row.reporterUserId}`,
    ),
    h(
      'p',
      { class: 'm-0 mt-2 text-12px', style: 'color: var(--c-text-2); word-break: break-word' },
      row.detail ? `举报详情：${row.detail}` : '举报人未填写详情',
    ),
    h('div', { class: 'mt-3' }, [
      h('div', { class: 'c-muted text-12px mb-1' }, '处理备注（写进审计 detail.note，可留空）'),
      h(NInput, {
        value: note.value,
        type: 'textarea',
        rows: 3,
        maxlength: 500,
        placeholder: '例如：与审核单 #123 合并处理',
        'onUpdate:value': (value: string) => {
          note.value = value
        },
      }),
    ]),
  ])
}

function openHandle(row: ModerationReportRow, action: HandleAction): void {
  const meta = ACTION_META[action]
  const note = ref('')
  dialog.info({
    title: `${meta.title}（举报 #${row.id}）`,
    content: () => dialogBody(row, action, note),
    positiveText: meta.label,
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const updated = await callHandle(row.id, action, note.value)
        message.success(
          updated.caseId === null
            ? `举报 #${row.id} 已${meta.label}`
            : `举报 #${row.id} 已${meta.label}，关联审核单 #${updated.caseId}`,
        )
        await reports.load()
      } catch (err) {
        handleFailure(err)
      }
      return true
    },
  })
}

function caseCell(row: ModerationReportRow): VNodeChild {
  const caseId = row.caseId
  if (caseId === null) {
    return h('span', { class: 'c-weak', title: '受理举报后会建立或关联审核单' }, '—')
  }
  return h(
    NButton,
    { size: 'tiny', quaternary: true, type: 'primary', onClick: () => goQueue(caseId) },
    { default: () => `审核单 #${caseId}` },
  )
}

function actionCell(row: ModerationReportRow): VNodeChild {
  if (row.status !== 'pending') {
    return h('span', { class: 'c-weak', title: `处理时间 ${fmtDateTime(row.handledAt)}` }, '已处理')
  }
  const buttons = (['accept', 'reject', 'duplicate'] as HandleAction[]).map((action) =>
    h(
      NButton,
      {
        size: 'tiny',
        quaternary: true,
        type: action === 'accept' ? 'primary' : 'default',
        onClick: () => openHandle(row, action),
      },
      { default: () => ACTION_META[action].label },
    ),
  )
  // 写操作统一挂权限门（UX 裁剪；后端逐请求校验才是安全边界，docs/50 §4.3）
  return h(
    PermissionGate,
    { code: 'moderation:report:handle' },
    { default: () => h('span', { class: 'mr-actions' }, buttons) },
  )
}

const columns = computed<DataTableColumns<ModerationReportRow>>(() => [
  {
    title: '举报人',
    key: 'reporterUserId',
    width: 108,
    // 列表只给用户 id：服务端不过昵称（隐私收敛），不编造显示名
    render: (row) => h('span', { class: 'c-mono', title: '服务端只回传用户 id' }, `用户 #${row.reporterUserId}`),
  },
  {
    title: '目标',
    key: 'target',
    width: 128,
    render: (row) =>
      h('span', {}, [
        h('span', { class: 'c-muted' }, TARGET_TYPE_LABEL[row.targetType] ?? row.targetType),
        h('span', { class: 'c-mono mr-target-id' }, `#${row.targetId}`),
      ]),
  },
  {
    title: '原因码',
    key: 'reasonCode',
    width: 108,
    render: (row) => h('span', { title: row.reasonCode }, reasonCodeText(row.reasonCode)),
  },
  {
    title: '详情',
    key: 'detail',
    minWidth: 220,
    render: (row) => h('span', { class: 'mr-detail', title: row.detail ?? '' }, row.detail || '—'),
  },
  {
    title: '状态',
    key: 'status',
    width: 94,
    render: (row) => {
      const meta = REPORT_STATUS_META[row.status] ?? { text: row.status, tone: 'muted' }
      return h('span', { class: `c-badge c-badge--${meta.tone}` }, meta.text)
    },
  },
  { title: '关联审核单', key: 'caseId', width: 132, render: (row) => caseCell(row) },
  {
    title: '提交时间',
    key: 'createdAt',
    width: 168,
    render: (row) =>
      h('span', { class: 'c-num', title: fmtRelative(row.createdAt) }, fmtDateTime(row.createdAt)),
  },
  { title: '操作', key: 'actions', width: 176, render: (row) => actionCell(row) },
])
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="举报处理"
      desc="举报是审核单的上游：受理会建立或关联审核单，不成立与判重只关闭举报、不改动内容。举报详情为用户原文，仅作文本渲染。"
    >
      <template #actions>
        <span v-if="!canHandle" class="c-badge c-badge--muted">只读（需 moderation:report:handle）</span>
      </template>
    </PageHeader>

    <section class="c-card">
      <div class="c-card-head">
        <div>
          <h2 class="c-card-title">举报列表</h2>
          <p class="c-card-sub">
            默认只看待处理；「关联审核单」列可一键跳到待审队列并打开该单（举报本身的处置不等于内容已处置）
          </p>
        </div>
        <div class="mr-filters">
          <n-select
            v-model:value="reports.filters.value.status"
            class="mr-filter"
            size="small"
            :options="[{ label: '全部状态', value: '' }, ...REPORT_STATUS_OPTIONS]"
            @update:value="reports.applyFilters({})"
          />
          <n-button size="small" quaternary @click="reports.load()">刷新</n-button>
        </div>
      </div>

      <AsyncBlock
        :loading="reports.loading.value"
        :error="reports.error.value"
        :error-code="reports.errorCode.value"
        :empty="!reports.items.value.length"
        empty-text="没有符合条件的举报"
        empty-hint="C 端举报入口由 Python 侧提供（本期尚未接入），当前举报多来自手工建单与联调"
        :min-height="200"
      >
        <n-data-table
          :columns="columns"
          :data="reports.items.value"
          :row-key="(row: ModerationReportRow) => row.id"
          size="small"
          :bordered="false"
        />
        <div class="mr-pager">
          <span class="c-weak">共 {{ fmtInt(reports.total.value) }} 条</span>
          <n-button
            size="small"
            quaternary
            :disabled="reports.page.value <= 1"
            @click="reports.goPage(reports.page.value - 1)"
          >
            上一页
          </n-button>
          <span class="c-num">{{ reports.page.value }} / {{ reports.pageCount.value }}</span>
          <n-button
            size="small"
            quaternary
            :disabled="reports.page.value >= reports.pageCount.value"
            @click="reports.goPage(reports.page.value + 1)"
          >
            下一页
          </n-button>
        </div>
      </AsyncBlock>
    </section>
  </div>
</template>

<style scoped>
.mr-filters {
  display: flex;
  gap: 6px;
}
.mr-filter {
  width: 138px;
}
.mr-target-id {
  margin-left: 5px;
  font-size: 12px;
  color: var(--c-text-2);
}
.mr-detail {
  display: block;
  max-width: 100%;
  font-size: 12px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.mr-actions {
  display: inline-flex;
  gap: 2px;
}
.mr-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 10px;
  font-size: 12.5px;
}
</style>
