<script setup lang="ts">
/**
 * **Trace 瀑布** —— 库外图型，走 SKILL §6「翻译流程」（docs/50 §12.3）。
 *
 * 第 1 步 · 先回答本体（每个视觉通道编码什么）：
 *   横向位置 = 绝对时间（以 trace 起点为原点）
 *   条形长度 = span 耗时 → **长度∝时间，绝不截断**
 *   纵向缩进 = span 树层级（parent_span_id，每层 14px）
 *   **明度 = 状态**（Mono 无彩色，故状态只能靠明度 + 端头标记，不靠色相）
 *   内部细分隔线 = `ttft_ms`（首 token 延迟，落在 LLM span 内部）
 *
 * 第 2 步 · 最近亲 = **L11 Trend Lineage**（`lupi-gallery.html` ·
 *   卡内标题 `Features rise, fall, come back`，事件序列生命史）——
 *   它已有「横向时间轴 + 每实体一行 + 状态编码 + 旁注」的语法，正是 span 生命史的形状。
 *   继承其布局骨架与动画节奏，不发明新的视觉语言。
 *
 * 第 3 步 · token 造句：颜色/字号/圆角/动效全部取自 `mono.ts`，与库内图"一眼一家人"。
 *
 * 第 4 步 · 交互三问（SKILL §5）：
 *   ① 每根条背后有真实 span 记录 ✔ ② 条数常 >50，「不点读不出来」✔
 *   ③ → **必须 hover/pin**：hover 高亮整棵子树，点击钉住，再点取消。
 *
 * 为什么这里用 ResizeObserver 而不是 `viewBox + preserveAspectRatio="none"`：
 * 瀑布里条的**长度本身就是数据**，横向非等比拉伸会让"圆角端头"和"发丝线"变形，
 * 破坏长度∝时间的读法。真实像素坐标是这里唯一诚实的做法。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import type { TraceSpan } from '@/api'

import { mono } from './mono'

const props = defineProps<{ spans: TraceSpan[]; originAt: string }>()

const ROW_H = 22
const INDENT = 14
const LABEL_W = 208
/**
 * 亚像素 span 的最小可见宽度。
 *
 * ⚠️ 这**违反**"长度∝时间"的字面契约（UI 拷问 P0-5 指出），但它是 SKILL §7 明确允许的
 * 三条诚实方案里的第 ③ 条——「**撕柱不撕轴**，并明说画不下」：
 *   ① 让极端值冲天（此处即 0.18px，等于看不见）② 主图+放大镜小图 ③ 撕柱不撕轴 + 明说
 * 30s 的 trace 画在 ~270px 轴上时 1px ≈ 110ms，一个 20ms 的 span 真实宽度是 0.18px。
 * 取 ③ 的代价是"最短的条被读成很短"，收益是"它至少存在、可 hover、可点开看精确值"。
 * **因此这个最小值必须在界面上写明**（见模板里的 `.tw-foot`），不能悄悄加——
 * 悄悄加就是"静默说谎"，那不在这三条里。
 */
const MIN_BAR = 1.5

const host = ref<HTMLElement | null>(null)
const lanes = ref(600)
let ro: ResizeObserver | null = null

onMounted(() => {
  const node = host.value
  if (!node) return
  if (typeof ResizeObserver === 'undefined') {
    lanes.value = Math.max(240, node.clientWidth - LABEL_W)
    return
  }
  ro = new ResizeObserver((entries) => {
    const w = entries[0]?.contentRect.width ?? 0
    lanes.value = Math.max(240, w - LABEL_W)
  })
  ro.observe(node)
})

onBeforeUnmount(() => {
  ro?.disconnect()
  ro = null
})

/** 时间原点：显式传入优先（调用方传 trace.started_at），否则取所有 span 的最早起点 */
const origin = computed(() => {
  const explicit = new Date(props.originAt).getTime()
  if (Number.isFinite(explicit)) return explicit
  // started_at 在视图层可能为 null（ops.py:757 的 `row.started_at.isoformat() if row.started_at else None`）
  const starts = props.spans
    .map((s) => (s.started_at ? new Date(s.started_at).getTime() : Number.NaN))
    .filter((v) => Number.isFinite(v))
  return starts.length ? Math.min(...starts) : Date.now()
})

const originMs = origin

interface Row {
  span: TraceSpan
  depth: number
  offset: number
  width: number
  color: string
  /** 端头标记：错误/中断需要一眼看出来 */
  marker: '' | 'error' | 'aborted'
  /** TTFT 分隔线的横向位置（相对条起点，px），null = 无 */
  ttftX: number | null
}

function statusColor(status: TraceSpan['status']): string {
  if (status === 'ok') return mono.L[0]
  if (status === 'aborted') return mono.L[4]
  if (status === 'incomplete') return mono.L[3]
  return mono.L[1]
}

/** 由 parent_span_id 还原树，按 DFS 摊平成行（保证子节点紧跟父节点） */
function buildRows(spans: TraceSpan[]): Row[] {
  const byId = new Map(spans.map((s) => [s.span_id, s]))
  const children = new Map<string | null, TraceSpan[]>()
  for (const s of spans) {
    const pid = s.parent_span_id && byId.has(s.parent_span_id) ? s.parent_span_id : null
    const list = children.get(pid) ?? []
    list.push(s)
    children.set(pid, list)
  }
  for (const list of children.values()) list.sort((a, b) => a.seq - b.seq)

  const startOf = (s: TraceSpan) =>
    s.started_at ? new Date(s.started_at).getTime() - originMs.value : 0
  const ends = spans.map((s) => startOf(s) + (s.duration_ms ?? 0))
  const total = Math.max(...ends, 1)
  const laneW = lanes.value

  const rows: Row[] = []
  const walk = (parentId: string | null, depth: number): void => {
    for (const s of children.get(parentId) ?? []) {
      const offset = Math.max(0, startOf(s))
      const raw = s.duration_ms ?? 0
      const width = Math.max(MIN_BAR, (raw / total) * laneW)
      rows.push({
        span: s,
        depth,
        offset: (offset / total) * laneW,
        width: Math.min(width, laneW),
        color: statusColor(s.status),
        marker: s.status === 'ok' ? '' : s.status === 'aborted' ? 'aborted' : 'error',
        ttftX: s.ttft_ms !== null && s.ttft_ms > 0 ? Math.min((s.ttft_ms / Math.max(raw, 1)) * width, width) : null,
      })
      walk(s.span_id, depth + 1)
    }
  }
  walk(null, 0)
  // 孤儿 span（父不在集合内）已在 children[null] 中，会被 walk 覆盖
  return rows
}

const rows = computed(() => buildRows(props.spans))
const totalMs = computed(() => {
  const ends = props.spans.map((s) =>
    s.started_at
      ? new Date(s.started_at).getTime() - originMs.value + (s.duration_ms ?? 0)
      : (s.duration_ms ?? 0),
  )
  return Math.max(...ends, 1)
})

/** 刻度：4 条等分导轨，跑在图表下方作"家具"（SKILL §3 环境结构层） */
const gridLines = computed(() =>
  [0, 0.25, 0.5, 0.75, 1].map((r) => ({ ratio: r, x: r * lanes.value, label: `${Math.round(r * totalMs.value)}ms` })),
)

// ── 交互：hover 高亮子树，点击钉住 ────────────────────────────────────────
const hovered = ref<string | null>(null)
const pinned = ref<string | null>(null)
const focusId = computed(() => pinned.value ?? hovered.value)

const subtree = computed<Set<string>>(() => {
  const root = focusId.value
  if (!root) return new Set()
  const children = new Map<string, string[]>()
  for (const s of props.spans) {
    if (!s.parent_span_id) continue
    const list = children.get(s.parent_span_id) ?? []
    list.push(s.span_id)
    children.set(s.parent_span_id, list)
  }
  const out = new Set<string>([root])
  const stack = [root]
  while (stack.length) {
    const id = stack.pop() as string
    for (const child of children.get(id) ?? []) {
      if (!out.has(child)) {
        out.add(child)
        stack.push(child)
      }
    }
  }
  return out
})

function rowState(spanId: string): 'focus' | 'dim' | 'idle' {
  if (!focusId.value) return 'idle'
  return subtree.value.has(spanId) ? 'focus' : 'dim'
}

function togglePin(spanId: string): void {
  pinned.value = pinned.value === spanId ? null : spanId
}

function spanLabel(s: TraceSpan): string {
  const parts = [s.name]
  if (s.tool_name) parts.push(s.tool_name)
  if (s.retry_index > 0) parts.push(`重试#${s.retry_index}`)
  return parts.join(' · ')
}

function spanMeta(s: TraceSpan): string {
  const parts: string[] = []
  if (s.model) parts.push(s.model)
  if (s.prompt_tokens !== null || s.completion_tokens !== null) {
    parts.push(`${s.prompt_tokens ?? 0}/${s.completion_tokens ?? 0} tok`)
  }
  if (s.finish_reason && s.finish_reason !== 'stop') parts.push(s.finish_reason)
  return parts.join(' · ')
}
</script>

<template>
  <div ref="host" class="tw">
    <div class="tw-scale" :style="{ paddingLeft: `${LABEL_W}px` }">
      <span v-for="g in gridLines" :key="g.x" class="tw-scale-tick" :style="{ left: `${LABEL_W + g.x}px` }">
        {{ g.label }}
      </span>
    </div>

    <div class="tw-rows" :style="{ height: `${Math.max(rows.length, 1) * ROW_H}px` }">
      <!-- 纵向导轨（环境结构层） -->
      <span
        v-for="g in gridLines"
        :key="`grid-${g.x}`"
        class="tw-gridline"
        :style="{ left: `${LABEL_W + g.x}px` }"
        aria-hidden="true"
      />

      <div
        v-for="(row, i) in rows"
        :key="row.span.span_id"
        class="tw-row"
        :class="[`tw-row--${rowState(row.span.span_id)}`, pinned === row.span.span_id ? 'tw-row--pinned' : '']"
        :style="{ top: `${i * ROW_H}px`, height: `${ROW_H}px` }"
        role="button"
        tabindex="0"
        :aria-label="`${spanLabel(row.span)}，耗时 ${row.span.duration_ms ?? 0} 毫秒，状态 ${row.span.status}`"
        @mouseenter="hovered = row.span.span_id"
        @mouseleave="hovered = null"
        @click="togglePin(row.span.span_id)"
        @keydown.enter.prevent="togglePin(row.span.span_id)"
        @keydown.space.prevent="togglePin(row.span.span_id)"
      >
        <!-- 左标签列 -->
        <span
          class="tw-label"
          :style="{ paddingLeft: `${8 + row.depth * INDENT}px`, width: `${LABEL_W}px` }"
          :title="`${spanLabel(row.span)}${spanMeta(row.span) ? ' · ' + spanMeta(row.span) : ''}`"
        >
          <i v-if="row.depth > 0" class="tw-elbow" aria-hidden="true" />
          {{ spanLabel(row.span) }}
          <em v-if="spanMeta(row.span)" class="tw-label-meta">{{ spanMeta(row.span) }}</em>
        </span>

        <!-- 时间条 -->
        <span
          class="tw-bar"
          :style="{
            left: `${LABEL_W + row.offset}px`,
            width: `${row.width}px`,
            background: row.color,
          }"
        >
          <span v-if="row.ttftX !== null" class="tw-ttft" :style="{ left: `${row.ttftX}px` }" aria-hidden="true" />
          <span v-if="row.marker" class="tw-mark" :class="`tw-mark--${row.marker}`" aria-hidden="true">
            {{ row.marker === 'error' ? '✕' : '‖' }}
          </span>
        </span>

        <span class="tw-dur" :style="{ left: `${LABEL_W + row.offset + row.width + 6}px` }">
          {{ row.span.duration_ms ?? 0 }}ms
        </span>
      </div>

      <p v-if="!rows.length" class="tw-empty">该 trace 没有 span（采集可能被关闭或已过保留期）</p>
    </div>

    <p class="tw-foot">
      长度 = 耗时（比例尺 1px ≈ {{ Math.round(totalMs / Math.max(lanes, 1)) }}ms，轴未截断） · 缩进 = 调用层级 ·
      明度 = 状态（越黑越正常，<i class="tw-swatch tw-swatch--ok" /> 成功
      <i class="tw-swatch tw-swatch--ab" /> 中断 <i class="tw-swatch tw-swatch--err" /> 失败） ·
      竖线 = TTFT（首 token 延迟） · 点击可钉住子树
    </p>
    <p class="tw-foot tw-foot--caveat">
      ⚠️ 短于 {{ Math.round((MIN_BAR * totalMs) / Math.max(lanes, 1)) }}ms 的 span 会被画成最小可见宽度
      {{ MIN_BAR }}px（"撕柱不撕轴"：宁可让最短的条被读成"很短"，也不压缩坐标轴）。
      精确耗时请看条右侧读数、悬停提示或下方 Span 明细表。
    </p>
  </div>
</template>

<style scoped>
.tw {
  --label-w: 208px;
  font-family: Inter, 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
  color: #1c1c1a;
}
.tw-scale {
  position: relative;
  height: 18px;
  font-size: 9.5px;
  font-weight: 600;
  color: #b0afa9;
}
.tw-scale-tick {
  position: absolute;
  transform: translateX(-50%);
  white-space: nowrap;
}
.tw-rows {
  position: relative;
  min-height: 22px;
}
.tw-gridline {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 0.5px;
  background: #deddd6;
}
.tw-row {
  position: absolute;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  cursor: pointer;
  transition: opacity 0.15s ease;
}
.tw-row--dim {
  opacity: 0.28;
}
.tw-row--pinned .tw-bar {
  box-shadow: 0 0 0 2px rgba(28, 28, 26, 0.18);
}
.tw-row:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px #e8edff;
  border-radius: 4px;
}
.tw-label {
  box-sizing: border-box;
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tw-elbow {
  width: 7px;
  height: 7px;
  border-left: 0.7px solid #b0afa9;
  border-bottom: 0.7px solid #b0afa9;
  border-bottom-left-radius: 3px;
  flex: 0 0 auto;
}
.tw-label-meta {
  font-style: normal;
  font-weight: 400;
  font-size: 10px;
  color: #8f8e88;
}
.tw-bar {
  position: absolute;
  top: 6px;
  height: 10px;
  border-radius: 5px;
  min-width: 1.5px;
  animation: tw-grow 0.5s cubic-bezier(0.25, 1, 0.5, 1) both;
  transform-origin: left center;
}
@keyframes tw-grow {
  from {
    transform: scaleX(0.02);
    opacity: 0;
  }
}
.tw-ttft {
  position: absolute;
  top: -1px;
  bottom: -1px;
  width: 1px;
  background: #f0efeb;
  opacity: 0.85;
}
.tw-mark {
  position: absolute;
  right: -12px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 9px;
  font-weight: 700;
}
.tw-mark--error {
  color: #1c1c1a;
}
.tw-mark--aborted {
  color: #8f8e88;
}
.tw-dur {
  position: absolute;
  font-size: 9.5px;
  font-weight: 600;
  color: #6a6963;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.tw-empty {
  margin: 0;
  padding: 24px 0;
  text-align: center;
  font-size: 12.5px;
  color: #8f8e88;
}
.tw-foot {
  margin: 12px 0 0;
  font-size: 10px;
  color: #6a6963;
  line-height: 1.7;
}
.tw-foot--caveat {
  margin-top: 4px;
  color: #6a6963;
}
.tw-swatch {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  vertical-align: -1px;
  margin: 0 2px 0 4px;
}
.tw-swatch--ok {
  background: #1c1c1a;
}
.tw-swatch--ab {
  background: #b0afa9;
}
.tw-swatch--err {
  background: #4a4944;
  border: 1px solid #1c1c1a;
}
@media (prefers-reduced-motion: reduce) {
  .tw-bar {
    animation: none;
  }
}
</style>
