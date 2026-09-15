<script setup lang="ts">
/**
 * 运维 · Trace 详情（docs/50 §7.2 / §7.5）。
 *
 * 页面三段，对应调优时的三个问题：
 *   ① 瀑布：**时间花在哪**（跨 ASR/LLM/TTS，看清塞在哪个环节）
 *   ② span 表：**具体哪一次调用**（模型、token、finish_reason、第几次重试）
 *   ③ 内容：**它到底说了什么**（需独立权限；未捕获时明确说"未捕获"而不是给空表）
 *
 * 隐私设计（§7.5）：内容页顶部常驻捕获状态条；读取内容会写审计——
 * 看别人的 prompt 是留痕行为，不是无痕操作。
 *
 * ⚠️ 形状按 ops.py:660-720 直读：详情是 `{trace, spans, truncated, span_limit}`（**没有 originAt**，
 * 瀑布原点用 `trace.started_at`）；内容是 `{captured, content_capture_enabled, deny_reason, items, total}`
 * （不是 `{captured, reason, rows}`）。
 */
import { computed, h, onMounted } from 'vue'
import { NDataTable } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import IconArrowLeft from '~icons/tabler/arrow-left'
import IconShieldLock from '~icons/tabler/shield-lock'

import { opsApi } from '@/api'
import type { TraceContentRow, TraceSpan } from '@/api'
import TraceWaterfall from '@/components/charts/TraceWaterfall.vue'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { useAsync } from '@/composables/useAsync'
import { fmtCompact, fmtDateTime, fmtInt, fmtMs } from '@/utils/format'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const traceId = computed(() => String(route.params.traceId ?? ''))
const detail = useAsync(() => opsApi.getTrace(traceId.value))
const contents = useAsync(() => opsApi.traceContents(traceId.value))

const canReadContent = computed(() => auth.hasPermission('ops:trace:content:read'))
const t = computed(() => detail.state.value.data?.trace)
const spans = computed(() => detail.state.value.data?.spans ?? [])
const truncated = computed(() => detail.state.value.data?.truncated ?? false)
const spanLimit = computed(() => detail.state.value.data?.span_limit ?? null)
/** 瀑布原点 = trace 起点（trace 与根 span 同起；后端不返回 originAt 字段） */
const originAt = computed(() => t.value?.started_at ?? '')

/** "没采到"的说明：优先用后端 deny_reason，其次按当前开关状态给出可操作的解释 */
const uncapturedNote = computed(() => {
  const data = contents.state.value.data
  if (!data) return ''
  if (data.deny_reason) return data.deny_reason
  return data.content_capture_enabled
    ? '采集器报告本 trace 未捕获内容。'
    : '服务端内容捕获开关当前为关闭状态（APP_LLM_TRACE_CONTENT_CAPTURE=false）。'
})

async function loadContents(): Promise<void> {
  if (canReadContent.value) await contents.run()
}

onMounted(async () => {
  await detail.run()
  await loadContents()
})

function back(): void {
  void router.push('/ops/traces')
}

const spanColumns = computed<DataTableColumns<TraceSpan>>(() => [
  {
    title: 'Span',
    key: 'name',
    width: 190,
    render: (row) =>
      h('span', {}, [
        h('span', { class: 'c-mono' }, row.name),
        row.tool_name ? h('span', { class: 'c-weak' }, ` · ${row.tool_name}`) : null,
        row.retry_index > 0 ? h('span', { class: 'c-badge c-badge--warn', style: 'margin-left:6px' }, `重试#${row.retry_index}`) : null,
      ]),
  },
  { title: '类型', key: 'span_kind', width: 84, render: (row) => h('span', { class: 'c-weak' }, row.span_kind) },
  { title: '状态', key: 'status', width: 84, render: (row) => h(StatusBadge, { kind: 'trace', value: row.status }) },
  { title: '耗时', key: 'duration_ms', width: 92, render: (row) => h('span', { class: 'c-num' }, fmtMs(row.duration_ms)) },
  {
    title: 'TTFT',
    key: 'ttft_ms',
    width: 84,
    render: (row) => h('span', { class: 'c-num' }, row.ttft_ms === null ? '—' : fmtMs(row.ttft_ms)),
  },
  { title: '模型', key: 'model', width: 148, render: (row) => h('span', { class: 'c-mono' }, row.model ?? '—') },
  {
    title: 'Token 入/出',
    key: 'tokens',
    width: 110,
    render: (row) =>
      row.prompt_tokens === null && row.completion_tokens === null
        ? h('span', { class: 'c-weak' }, '—')
        : h('span', { class: 'c-num' }, `${row.prompt_tokens ?? 0} / ${row.completion_tokens ?? 0}`),
  },
  {
    title: '结束原因',
    key: 'finish_reason',
    width: 118,
    render: (row) => {
      if (!row.finish_reason) return h('span', { class: 'c-weak' }, '—')
      const warn = row.finish_reason !== 'stop'
      return h('span', { class: `c-badge c-badge--${warn ? 'warn' : 'ok'}` }, row.finish_reason)
    },
  },
  {
    title: '错误',
    key: 'error',
    minWidth: 160,
    ellipsis: { tooltip: true },
    render: (row) => (row.error_code ? h('span', { class: 'c-mono' }, `${row.error_code}: ${row.error_message ?? ''}`) : h('span', { class: 'c-weak' }, '—')),
  },
])

const contentColumns = computed<DataTableColumns<TraceContentRow>>(() => [
  { title: 'Span', key: 'span_id', width: 108, render: (row) => h('span', { class: 'c-mono' }, row.span_id) },
  { title: '方向', key: 'direction', width: 70, render: (row) => h('span', {}, row.direction === 'input' ? '入' : '出') },
  { title: '角色', key: 'role', width: 84, render: (row) => h('span', { class: 'c-mono' }, row.role ?? '—') },
  {
    title: '内容',
    key: 'content',
    minWidth: 320,
    render: (row) =>
      h('span', {}, [
        row.redacted ? h('span', { class: 'c-badge c-badge--warn', style: 'margin-right:6px' }, '已脱敏') : null,
        row.truncated ? h('span', { class: 'c-badge c-badge--muted', style: 'margin-right:6px' }, '已截断') : null,
        // 纯文本插值：绝不 v-html（docs/13:83 存储型 XSS 红线）
        h('span', { class: 'tc-content' }, row.content),
      ]),
  },
  { title: '字符数', key: 'content_chars', width: 84, render: (row) => h('span', { class: 'c-num' }, fmtInt(row.content_chars)) },
])
</script>

<template>
  <div class="c-page">
    <button class="tc-back" type="button" @click="back">
      <IconArrowLeft width="15" height="15" aria-hidden="true" />
      返回列表
    </button>

    <PageHeader
      title="Trace 详情"
      :desc="t ? `${t.kind} · ${t.model ?? '未知模型'} · ${fmtDateTime(t.started_at)}` : traceId"
    >
      <template #actions>
        <StatusBadge v-if="t" kind="trace" :value="t.status" />
      </template>
    </PageHeader>

    <AsyncBlock
      :loading="detail.state.value.loading"
      :error="detail.state.value.error"
      :error-code="detail.state.value.errorCode"
      :empty="!t"
      empty-text="Trace 不存在或已过保留期"
      empty-hint="trace 默认保留 30 天（内容 72 小时）"
      :min-height="240"
    >
      <div v-if="t" class="tc-stack">
        <div class="c-stat-row">
          <div class="c-stat">
            <div class="c-stat-label">Trace ID</div>
            <div class="c-stat-value tc-id">{{ t.trace_id }}</div>
            <div class="c-stat-delta">{{ t.request_id ? `request-id ${t.request_id}` : '无关联 request-id' }}</div>
          </div>
          <div class="c-stat">
            <div class="c-stat-label">总耗时</div>
            <div class="c-stat-value">{{ fmtMs(t.duration_ms) }}</div>
            <div class="c-stat-delta">
              首 token {{ t.ttft_ms === null ? '—' : fmtMs(t.ttft_ms) }} · {{ t.span_count }} span / {{ t.llm_call_count }} 次 LLM
            </div>
          </div>
          <div class="c-stat">
            <div class="c-stat-label">Token</div>
            <div class="c-stat-value">{{ fmtCompact(t.total_tokens) }}</div>
            <div class="c-stat-delta">入 {{ fmtInt(t.prompt_tokens) }} / 出 {{ fmtInt(t.completion_tokens) }}</div>
          </div>
          <div class="c-stat">
            <div class="c-stat-label">会话</div>
            <div class="c-stat-value tc-session">{{ t.session_id ?? '—' }}</div>
            <div class="c-stat-delta">{{ t.user_id === null ? '无用户上下文' : `用户 #${t.user_id}` }}</div>
          </div>
        </div>

        <p v-if="t.error_code || t.error_message" class="tc-error" role="alert">
          <strong>{{ t.error_code ?? '错误' }}</strong> {{ t.error_message ?? '' }}
        </p>

        <!-- ① 瀑布：时间花在哪 -->
        <section class="c-card tc-mono-card">
          <div class="c-card-head">
            <div>
              <h2 class="c-card-title">时间花在哪</h2>
              <p class="c-card-sub">
                长度 = 耗时（未截断）· 缩进 = 调用层级 · 明度 = 状态 · 竖线 = TTFT ·
                悬停高亮子树，点击钉住
              </p>
            </div>
          </div>
          <TraceWaterfall :spans="spans" :origin-at="originAt" />
        </section>

        <!-- ② span 表：具体哪一次调用 -->
        <section class="c-card">
          <div class="c-card-head">
            <div>
              <h2 class="c-card-title">Span 明细</h2>
              <p class="c-card-sub">
                每次真实 LLM 尝试各占一行；「重试#N」表示同一 STEP 下的第 N 次尝试（失败尝试也留痕）
              </p>
            </div>
            <span v-if="truncated" class="c-badge c-badge--warn">
              已截断：只取前 {{ spanLimit }} 个 span（后端硬上限 500）
            </span>
          </div>
          <n-data-table
            :columns="spanColumns"
            :data="spans"
            :row-key="(row: TraceSpan) => row.span_id"
            size="small"
            :bordered="false"
            :max-height="420"
            virtual-scroll
          />
        </section>

        <!-- ③ 内容：它到底说了什么（独立权限） -->
        <section class="c-card">
          <div class="c-card-head">
            <div>
              <h2 class="c-card-title">内容捕获</h2>
              <p class="c-card-sub">
                读取内容会写入审计日志（谁在什么时候看了哪条 trace 的内容）
              </p>
            </div>
            <span class="c-badge" :class="t.content_captured ? 'c-badge--warn' : 'c-badge--muted'">
              {{ t.content_captured ? '本 trace 已捕获内容' : '本 trace 未捕获内容' }}
            </span>
          </div>

          <div v-if="!canReadContent" class="tc-locked">
            <IconShieldLock width="18" height="18" aria-hidden="true" />
            <div>
              <p class="tc-locked-title">需要额外权限才能查看内容</p>
              <p class="tc-locked-desc">
                你的账号缺少 <code>ops:trace:content:read</code>。
                结构元数据（模型、token、耗时）不需要该权限 —— 只看性能不必看用户对话内容。
              </p>
            </div>
          </div>

          <template v-else>
            <AsyncBlock
              :loading="contents.state.value.loading"
              :error="contents.state.value.error"
              :error-code="contents.state.value.errorCode"
              :empty="!(contents.state.value.data?.items ?? []).length"
              empty-text="本 trace 没有捕获到内容"
              empty-hint="内容捕获默认关闭（APP_LLM_TRACE_CONTENT_CAPTURE=false）；开启后仅新产生的 trace 才有内容"
              :min-height="120"
            >
              <p v-if="!contents.state.value.data?.captured" class="tc-note">{{ uncapturedNote }}</p>
              <n-data-table
                :columns="contentColumns"
                :data="contents.state.value.data?.items ?? []"
                :row-key="(row: TraceContentRow) => `${row.span_id}-${row.direction}-${row.seq}`"
                size="small"
                :bordered="false"
                :max-height="420"
              />
            </AsyncBlock>
          </template>
        </section>
      </div>
    </AsyncBlock>
  </div>
</template>

<style scoped>
.tc-back {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 12px;
  padding: 4px 10px 4px 6px;
  border: 0;
  border-radius: var(--c-ctl-radius);
  background: transparent;
  color: var(--c-text-2);
  font-size: 12.5px;
  cursor: pointer;
  transition: background var(--vv-t-micro) var(--vv-ease-out);
}
.tc-back:hover {
  background: var(--c-surface-sunken);
  color: var(--c-text);
}
.tc-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.tc-id,
.tc-session {
  font-family: var(--vv-font-mono);
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tc-error {
  margin: 0;
  padding: 10px 14px;
  border-radius: var(--c-ctl-radius);
  background: var(--c-danger-soft);
  color: var(--c-danger);
  font-size: 12.5px;
}
/* 瀑布卡跟随 Mono 纸底：Mono 的卡片契约是"卡底 = 页面底，靠留白分卡" */
.tc-mono-card {
  background: #f0efeb;
  box-shadow: none;
}
.tc-mono-card .c-card-title {
  color: #1c1c1a;
}
.tc-mono-card .c-card-sub {
  color: #8f8e88;
}
.tc-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.6;
  display: block;
  max-height: 200px;
  overflow: auto;
}
.tc-note {
  margin: 0 0 10px;
  font-size: 12.5px;
  color: var(--c-text-2);
}
.tc-locked {
  display: flex;
  gap: 10px;
  padding: 14px;
  border-radius: var(--c-ctl-radius);
  background: var(--c-surface-sunken);
  color: var(--c-text-2);
}
.tc-locked-title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--c-text);
}
.tc-locked-desc {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
}
.tc-locked code {
  font-family: var(--vv-font-mono);
  background: var(--c-surface);
  padding: 1px 5px;
  border-radius: 4px;
}
</style>
