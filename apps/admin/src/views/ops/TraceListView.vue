<script setup lang="ts">
/**
 * 运维 · LLM Trace 列表（docs/50 §7 / §10.3）。
 *
 * 这张页面的用途是**后续调优的取样入口**：先按"慢 / 错 / 某模型 / 某会话"
 * 缩小范围，再进详情看 span 树。因此筛选维度比列更重要——
 * 列只放"决定要不要点进去"的信息，其余留给详情页。
 *
 * 隐私：列表**只展示结构元数据**（模型、token、耗时、状态），
 * 内容（prompt/response）在详情页且需要独立的 `ops:trace:content:read` 权限。
 *
 * ⚠️ 字段与查询参数按 `services/python/app/console/api/routes/ops.py` 逐字对齐：
 * - `/ops/traces/stats` 返回窗口汇总 + **按日趋势（`trend`）/ 按模型（`by_model`）/ 按状态（`by_status`）**。
 *   ⚠️ 修订记录：`trend`/`by_model` **曾经不存在**，本页的两张图因此被删过一轮；
 *   处置是**回派后端扩接口**而不是接受损失（`docs/50 §10.1.1` 第 3 条）。
 *   `trend[].duration_ms_p95` 为 `null` 表示该日无直方图样本——**图上留缺口，不画 0**。
 * - 列表查询参数是 `session_id` / `min_duration_ms`（ops.py:583-586），不是 sessionId / minDurationMs；
 * - 列表与统计卡共用同一个时间窗，否则"卡说近 14 天、表只查 1 天"会自相矛盾。
 */
import { computed, h, onMounted } from 'vue'
import { NButton, NDataTable } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { useRouter } from 'vue-router'

import { opsApi } from '@/api'
import type { TraceRow } from '@/api'
import ChartCard from '@/components/charts/ChartCard.vue'
import HairlineLine from '@/components/charts/HairlineLine.vue'
import RungBars from '@/components/charts/RungBars.vue'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatTile from '@/components/common/StatTile.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { debounce, useAsync } from '@/composables/useAsync'
import { usePagedList } from '@/composables/usePagedList'
import { fmtCompact, fmtDateTime, fmtInt, fmtMs, fmtPercent, lastDaysRange } from '@/utils/format'

const router = useRouter()

const WINDOW_DAYS = 14
/** 统计卡与列表共用这一个窗口（from/to 是后端真实参数，默认只查最近 1 天） */
const range = lastDaysRange(WINDOW_DAYS)

const stats = useAsync(() => opsApi.traceStats(range))
const traces = usePagedList<
  TraceRow,
  { kind: string; status: string; model: string; session_id: string; min_duration_ms: string }
>(
  (q) =>
    opsApi.listTraces({
      ...q,
      from: range.from,
      to: range.to,
      min_duration_ms: q.min_duration_ms ? Number(q.min_duration_ms) : undefined,
    }),
  { kind: '', status: '', model: '', session_id: '', min_duration_ms: '' },
)

onMounted(async () => {
  await Promise.all([stats.run(), traces.load()])
})

const s = computed(() => stats.state.value.data)

/** 趋势横轴：`MM-DD`。后端已按 UTC 日补零成连续序列，这里不再去重/排序 */
const trendLabels = computed(() => (s.value?.trend ?? []).map((p) => p.date.slice(5)))

/**
 * 时长曲线是否可画。
 * `trend_meta.p95_available=false` 表示直方图行数超预算 → 该次响应 p95 **全为 null**。
 * 这种情况必须**说明原因**而不是画一张空图：空图会被读成"没有慢调用"，而真相是"这次没算"。
 */
const p95Available = computed(
  () => (s.value?.trend_meta?.p95_available ?? false) && (s.value?.trend ?? []).some((p) => p.duration_ms_p95 !== null),
)

/** 文本筛选防抖：避免每敲一个字符打一次接口 */
const onSearchInput = debounce((value: string) => void traces.applyFilters({ session_id: value.trim() }), 350)

const KIND_LABEL: Record<string, string> = {
  turn: '场景回合',
  free_chat: '自由说',
  defense: '答辩导师',
  summary: '收尾总结',
  conclude: '收尾判定',
  reading_tts: '听书合成',
  score: '评分',
  meta: 'META 补偿',
}

const columns = computed<DataTableColumns<TraceRow>>(() => [
  {
    title: '时间',
    key: 'started_at',
    width: 168,
    render: (row) => h('span', { class: 'c-num' }, fmtDateTime(row.started_at)),
  },
  { title: '类型', key: 'kind', width: 104, render: (row) => h('span', {}, KIND_LABEL[row.kind] ?? row.kind) },
  { title: '模型', key: 'model', width: 150, render: (row) => h('span', { class: 'c-mono' }, row.model ?? '—') },
  {
    title: '状态',
    key: 'status',
    width: 88,
    render: (row) => h(StatusBadge, { kind: 'trace', value: row.status }),
  },
  {
    title: '耗时',
    key: 'duration_ms',
    width: 96,
    sorter: (a, b) => (a.duration_ms ?? 0) - (b.duration_ms ?? 0),
    render: (row) => h('span', { class: 'c-num' }, fmtMs(row.duration_ms)),
  },
  {
    title: 'TTFT',
    key: 'ttft_ms',
    width: 88,
    render: (row) => h('span', { class: 'c-num' }, row.ttft_ms === null ? '—' : fmtMs(row.ttft_ms)),
  },
  {
    title: 'LLM 次数',
    key: 'llm_call_count',
    width: 84,
    render: (row) =>
      h('span', { class: 'c-num', title: `${row.span_count} 个 span` }, String(row.llm_call_count)),
  },
  {
    title: 'Token',
    key: 'total_tokens',
    width: 92,
    render: (row) => h('span', { class: 'c-num' }, fmtCompact(row.total_tokens)),
  },
  {
    title: '内容',
    key: 'content_captured',
    width: 80,
    render: (row) =>
      h(
        'span',
        { class: `c-badge c-badge--${row.content_captured ? 'warn' : 'muted'}` },
        row.content_captured ? '已捕获' : '未捕获',
      ),
  },
  {
    title: '',
    key: 'open',
    width: 78,
    render: (row) =>
      h(
        NButton,
        { size: 'tiny', quaternary: true, type: 'primary', onClick: () => void open(row) },
        { default: () => '详情' },
      ),
  },
])

async function open(row: TraceRow): Promise<void> {
  await router.push(`/ops/traces/${row.trace_id}`)
}
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="LLM Trace"
      desc="一次调用链 = 一个 trace；每次真实 LLM 尝试 = 一个 span（重试在同一 STEP 下可见）。列表只含结构元数据，内容需单独权限。"
    />

    <div class="c-stat-row" style="margin-bottom: 14px">
      <StatTile label="调用量" :value="s ? fmtInt(s.trace_count) : '—'" unit="条" :hint="`近 ${WINDOW_DAYS} 天`" :loading="stats.state.value.loading" />
      <StatTile
        label="错误率"
        :value="s ? fmtPercent(s.error_rate, 2) : '—'"
        :tone="s && s.error_rate > 0.1 ? 'danger' : undefined"
        :hint="s ? `失败 ${fmtInt(s.error_count)} / 总 ${fmtInt(s.trace_count)} 条` : '失败 trace / 总 trace'"
        :loading="stats.state.value.loading"
      />
      <StatTile
        label="耗时 p95"
        :value="s ? fmtMs(s.duration_ms_p95) : '—'"
        :hint="s?.duration_ms_p95_basis ?? '窗口内无直方图样本时后端拒绝给数'"
        :loading="stats.state.value.loading"
      />
      <StatTile
        label="LLM 调用次数"
        :value="s ? fmtInt(s.llm_call_count) : '—'"
        hint="含重试的每一次尝试"
        :loading="stats.state.value.loading"
      />
      <StatTile
        label="Token 消耗"
        :value="s ? fmtCompact(s.prompt_tokens + s.completion_tokens) : '—'"
        :hint="s ? `入 ${fmtCompact(s.prompt_tokens)} / 出 ${fmtCompact(s.completion_tokens)}` : ''"
        :loading="stats.state.value.loading"
      />
    </div>

    <div class="tl-grid">
      <ChartCard
        title="调用量在掉还是稳住了"
        sub="每日调用次数 · 失败数按 trace 终态 status=error|incomplete 归日 · 缺失日补 0（不跳过，否则折线会把断层画成斜坡）"
        chart-no="F2"
        template-title="Thirty days of sign-ups"
        source="llm_traces · /api/v1/console/ops/traces/stats"
        :height="200"
      >
        <template #default="{ revealed }">
          <HairlineLine
            :labels="trendLabels"
            :series="[
              { name: '调用', values: (s?.trend ?? []).map((p) => p.trace_count), tone: 0 },
              { name: '失败', values: (s?.trend ?? []).map((p) => p.error_count), tone: 2 },
            ]"
            unit=" 次"
            :format="(v: number) => fmtCompact(v)"
            :revealed="revealed"
          />
        </template>
      </ChartCard>

      <ChartCard
        title="哪个模型扛的活最多"
        sub="近 14 天调用量 · 横柱 = 该模型 trace 数 · 深色格 = 1 条 · `(unknown)` 表示 trace 未带主模型"
        chart-no="F1"
        template-title="Revenue by plan, rung by rung"
        source="llm_traces · by_model"
        :height="200"
      >
        <template #default="{ revealed }">
          <RungBars
            :items="(s?.by_model ?? []).map((m) => ({ label: m.model, value: m.trace_count }))"
            unit=" 条"
            :format-value="(v: number) => fmtInt(v)"
            :revealed="revealed"
          />
          <p v-if="!(s?.by_model ?? []).length" class="c-weak" style="font-size: 12.5px; margin: 0">
            近 {{ WINDOW_DAYS }} 天没有调用记录
          </p>
        </template>
      </ChartCard>
    </div>

    <!-- 时长 p95 单独一张：它是**分布型**指标，与计数不同轴，混在一张图里会读错量级 -->
    <ChartCard
      v-if="p95Available"
      title="端到端耗时是不是在变慢"
      sub="每日 trace 端到端 p95 · **由当日直方图合并后插值**（不是「每日 p95 再平均」）· 无样本日留缺口"
      chart-no="F2"
      template-title="Thirty days of sign-ups"
      source="llm_traces · trend[].duration_ms_p95"
      :height="190"
      wide
    >
      <template #default="{ revealed }">
        <HairlineLine
          :labels="trendLabels"
          :series="[{ name: 'p95', values: (s?.trend ?? []).map((p) => p.duration_ms_p95), tone: 0 }]"
          unit="ms"
          :format="(v: number) => fmtMs(v)"
          :revealed="revealed"
        />
      </template>
    </ChartCard>
    <section v-else class="c-card" style="margin-top: 14px">
      <h2 class="c-card-title">端到端耗时曲线本次不可用</h2>
      <p class="c-card-sub" style="margin: 0">
        {{ s?.trend_meta?.note ?? '后端未说明原因' }}（口径：{{ s?.trend_meta?.p95_metric ?? '—' }}，
        行预算 {{ s?.trend_meta?.rows_budget ?? '—' }}）。**这是有意的降级：宁可不画，也不返回基于部分直方图的错值。**
      </p>
    </section>

    <section class="c-card" style="margin-top: 14px">
      <div class="c-card-head">
        <div>
          <h2 class="c-card-title">Trace 查询</h2>
          <p class="c-card-sub">
            按类型 / 状态 / 模型 / 会话过滤；「最短耗时」用于把慢调用捞出来做调优样本 ·
            时间窗与上方卡片一致（近 {{ WINDOW_DAYS }} 天）
          </p>
        </div>
        <div class="tl-filters">
          <select v-model="traces.filters.value.kind" class="tl-select" @change="traces.applyFilters({})">
            <option value="">全部类型</option>
            <option v-for="(label, key) in KIND_LABEL" :key="key" :value="key">{{ label }}</option>
          </select>
          <select v-model="traces.filters.value.status" class="tl-select" @change="traces.applyFilters({})">
            <option value="">全部状态</option>
            <option value="ok">成功</option>
            <option value="error">失败</option>
            <option value="aborted">中断</option>
            <option value="incomplete">未完成</option>
          </select>
          <input
            class="tl-input"
            placeholder="模型名（如 deepseek-chat）"
            @input="(e) => traces.applyFilters({ model: (e.target as HTMLInputElement).value.trim() })"
          >
          <input
            class="tl-input"
            placeholder="会话 id"
            @input="(e) => onSearchInput((e.target as HTMLInputElement).value)"
          >
          <input
            v-model="traces.filters.value.min_duration_ms"
            class="tl-input tl-input--num"
            type="number"
            min="0"
            placeholder="最短耗时 ms"
            @change="traces.applyFilters({})"
          >
        </div>
      </div>

      <AsyncBlock
        :loading="traces.loading.value"
        :error="traces.error.value"
        :error-code="traces.errorCode.value"
        :empty="!traces.items.value.length"
        empty-text="没有符合条件的 trace"
        empty-hint="若刚部署：确认 APP_LLM_TRACE_ENABLED=true，并产生一次真实 LLM 调用"
        :min-height="200"
      >
        <n-data-table
          :columns="columns"
          :data="traces.items.value"
          :row-key="(row: TraceRow) => row.trace_id"
          size="small"
          :bordered="false"
        />
        <div class="tl-pager">
          <span class="c-weak">共 {{ fmtInt(traces.total.value) }} 条</span>
          <n-button size="small" quaternary :disabled="traces.page.value <= 1" @click="traces.goPage(traces.page.value - 1)">
            上一页
          </n-button>
          <span class="c-num">{{ traces.page.value }} / {{ traces.pageCount.value }}</span>
          <n-button
            size="small"
            quaternary
            :disabled="traces.page.value >= traces.pageCount.value"
            @click="traces.goPage(traces.page.value + 1)"
          >
            下一页
          </n-button>
        </div>
      </AsyncBlock>
    </section>
  </div>
</template>

<style scoped>
.tl-link {
  font-size: 12.5px;
  white-space: nowrap;
}
.tl-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tl-select,
.tl-input {
  height: 30px;
  border: 1px solid var(--c-border);
  border-radius: var(--c-ctl-radius);
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 12.5px;
  padding: 0 8px;
  font-family: inherit;
}
.tl-input {
  width: 170px;
}
.tl-input--num {
  width: 118px;
}
.tl-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 10px;
  font-size: 12.5px;
}
</style>
