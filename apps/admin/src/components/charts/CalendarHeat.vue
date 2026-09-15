<script setup lang="ts">
/**
 * **L17 Calendar Heat** — lieflat Lupi 编辑型（`catalog.md`：一整年 52 周 × 7 天 · 通栏 · SVG）。
 * 结构正本：`templates/lupi-gallery.html` · 卡内标题 `A year of deploys, day by day`
 * （渲染代码块 `// ════ L17 · calendar heat ════`，副标题 `dot area = deploys that day · tiny dot = a quiet day`）。
 *
 * 从该卡搬过来的结构：
 * - **54×7 的日历网格**（这里是 52 周 × 7 天），一格一天，**逐记录世界观**：
 *   一年 365 天每天都在场，"没有"也看得见（模板 `tiny dot = a quiet day`）；
 * - **点面积 = 当天量**（`areaRadius` 开方，不拿数值当半径）+ **最高日虚线圈**；
 * - 行名在左上（一/三/五/日），月份写在上檐并用小竖线钉住自己那一列；
 * - 明度 5 档（契约硬约束，模板只用 3 档）：分位切档，低档也有格子落进去。
 *
 * 契约要求的日历口径（模板是"第 w 周第 d 天"的合成数据，这里是真实日期）：
 * - **第一列前面留白对齐到周一**：首日之前的那几天不画点（缺席 ≠ 0），
 *   于是"第一列是哪一周"永远从周一开始，不会把周三错读成周一；
 * - **月份标签每 3 个月一个**（第一个标签列无条件标出，否则读者找不到参照）；
 * - 每格 `<title>` 给「YYYY-MM-DD　N」。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { bandLegend, quantileBands, shadeOfBand } from './bands'
import { areaRadius, mono } from './mono'

export interface CalendarDay {
  /** `YYYY-MM-DD`（也接受带时间的 ISO，只取日期部分） */
  date: string
  value: number
}

const props = withDefaults(
  defineProps<{
    days: CalendarDay[]
    unit?: string
    revealed?: boolean
  }>(),
  { unit: '', revealed: true },
)

/** 一年 52 周；多出一年则按实际周数画（并在脚注说明） */
const WEEKS_PER_YEAR = 52
/** 点距上限（px）：再大就不像日历了 */
const MAX_PITCH = 15
const ROW_LABELS: { dow: number; text: string }[] = [
  { dow: 0, text: '一' },
  { dow: 2, text: '三' },
  { dow: 4, text: '五' },
  { dow: 6, text: '日' },
]
const PAD_T = 26
const PAD_B = 18
const DAY_MS = 86_400_000

const host = ref<HTMLElement | null>(null)
const box = ref({ w: 760, h: 200 })
let ro: ResizeObserver | null = null

onMounted(() => {
  const node = host.value
  if (!node) return
  const read = (): void => {
    box.value = { w: Math.max(280, node.clientWidth), h: Math.max(110, node.clientHeight) }
  }
  read()
  if (typeof ResizeObserver === 'undefined') return
  ro = new ResizeObserver(read)
  ro.observe(node)
})

onBeforeUnmount(() => {
  ro?.disconnect()
  ro = null
})

/** `YYYY-MM-DD` → 本地 0 点时间戳 + 规范化的 `YYYY-MM-DD`（手写解析，避开 UTC 偏移） */
function parseDay(s: string): { ts: number; iso: string } | null {
  const m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(s)
  if (!m) return null
  const y = Number(m[1])
  const mo = Number(m[2])
  const d = Number(m[3])
  const dt = new Date(y, mo - 1, d)
  if (Number.isNaN(dt.getTime())) return null
  return { ts: dt.getTime(), iso: `${y}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}` }
}

interface Point {
  iso: string
  ts: number
  value: number
  week: number
  /** 0 = 周一 */
  dow: number
}

/** 摊平成"第几周 / 周几"：首日之前留白 → 第一列永远从周一开始；同一天重复上报只取首条 */
const points = computed<Point[]>(() => {
  const byIso = new Map<string, { ts: number; iso: string; value: number }>()
  for (const d of props.days) {
    const p = parseDay(d.date)
    if (p && Number.isFinite(d.value) && !byIso.has(p.iso)) byIso.set(p.iso, { ...p, value: d.value })
  }
  const parsed = [...byIso.values()].sort((a, b) => a.ts - b.ts)
  if (!parsed.length) return []
  const firstTs = parsed[0].ts
  const offset = (new Date(firstTs).getDay() + 6) % 7
  return parsed.map((d) => {
    const slot = Math.round((d.ts - firstTs) / DAY_MS) + offset
    return { iso: d.iso, ts: d.ts, value: d.value, week: Math.floor(slot / 7), dow: slot % 7 }
  })
})

const max = computed(() => (points.value.length ? Math.max(...points.value.map((p) => p.value)) : 0))
const hasData = computed(() => points.value.length > 0 && max.value > 0)
const weekCount = computed(() => (points.value.length ? Math.max(...points.value.map((p) => p.week)) + 1 : 0))
const thresholds = computed(() => quantileBands(points.value.map((p) => p.value)))

const geo = computed(() => {
  const { w, h } = box.value
  const innerH = Math.max(50, h - PAD_T - PAD_B)
  const pitch = Math.min(MAX_PITCH, Math.max(3, (w - 40) / Math.max(weekCount.value, WEEKS_PER_YEAR)))
  const gridW = pitch * weekCount.value
  // 不足一年时把网格居中：左对齐会显得"图没画完"
  const x0 = 26 + Math.max(0, (w - 32 - gridW) / 2)
  const rowH = Math.min(pitch, innerH / 7)
  return { w, h, x0, pitch, rowH, y0: PAD_T, rMax: Math.max(1.6, rowH * 0.42) }
})

interface Dot {
  key: string
  cx: number
  cy: number
  r: number
  shade: string
  quiet: boolean
  peak: boolean
  delay: number
  readout: string
}

const dots = computed<Dot[]>(() => {
  if (!hasData.value) return []
  const g = geo.value
  return points.value.map((p) => ({
    key: p.iso,
    cx: g.x0 + g.pitch * (p.week + 0.5),
    cy: g.y0 + g.rowH * (p.dow + 0.5),
    r: p.value > 0 ? Math.max(1.2, areaRadius(p.value, max.value, g.rMax)) : 0.75,
    shade: p.value > 0 ? shadeOfBand(p.value, thresholds.value) : mono.L[6],
    quiet: p.value <= 0,
    peak: p.value > 0 && p.value === max.value,
    delay: p.week * 12 + p.dow * 4,
    readout: `${p.iso}　${p.value}${props.unit}`,
  }))
})

const peakDot = computed(() => dots.value.find((d) => d.peak))
const peakPoint = computed(() => points.value.find((p) => p.value === max.value))

/** 月标签：每 3 个月一个；第一个标签列无条件标出（否则读者找不到参照） */
const monthMarks = computed(() => {
  const g = geo.value
  const pts = points.value
  const first = pts[0]
  if (!first) return []
  const offset = (new Date(first.ts).getDay() + 6) % 7
  /** 该周属于哪个月：优先看该周第一个真实数据点（周一的月份可能落在上一年 12 月） */
  const weekMonth = (wk: number): number => {
    const p = pts.find((x) => x.week === wk)
    const d = p ? new Date(p.ts) : new Date(first.ts - offset * DAY_MS + wk * 7 * DAY_MS)
    return d.getFullYear() * 12 + d.getMonth()
  }
  const out: { key: string; x: number; text: string }[] = []
  let lastLabeled = -9999
  for (let wk = 0; wk < weekCount.value; wk += 1) {
    const cur = weekMonth(wk)
    // 跨年时月份会从 11 跳回 0，所以用"年×12 + 月"的绝对月序比较，绝不能直接减 getMonth()
    if (wk !== 0 && cur === weekMonth(wk - 1)) continue
    if (out.length > 0 && cur - lastLabeled < 3) continue
    out.push({ key: `m-${wk}`, x: g.x0 + g.pitch * wk, text: `${(cur % 12) + 1}月` })
    lastLabeled = cur
  }
  return out
})

const legend = computed(() => bandLegend(thresholds.value, max.value))
const spanWeeks = computed(() => weekCount.value)
const footNote = computed(() => {
  if (!hasData.value) return ''
  const span = spanWeeks.value > WEEKS_PER_YEAR + 1 ? ` · 数据跨 ${spanWeeks.value} 周（超过一年，已按实际周数铺开）` : ''
  const peak = peakPoint.value
  return `点面积 = 当天数量 · 极小点 = 当日为 0（沉默可见） · 虚线环 = 全年峰值${
    peak ? ` ${peak.iso} ${peak.value}${props.unit}` : ''
  }${span}`
})
</script>

<template>
  <div v-if="!hasData" class="ch-empty">暂无数据（该区间没有可上日历的日子）</div>
  <div v-else ref="host" class="ch">
    <svg
      class="ch-svg"
      :width="geo.w"
      :height="geo.h"
      :viewBox="`0 0 ${geo.w} ${geo.h}`"
      role="img"
      :aria-label="`日历热力图，${spanWeeks} 周 × 7 天，峰值 ${max}${unit}`"
    >
      <g class="ch-g" :class="{ 'ch-g--in': revealed }">
        <!-- 行名（周一到周日，隔行标） -->
        <text
          v-for="r in ROW_LABELS"
          :key="`rw-${r.dow}`"
          class="ch-row"
          :x="geo.x0 - 6"
          text-anchor="end"
          :y="geo.y0 + geo.rowH * (r.dow + 0.5) + 2.4"
          font-size="6.5"
          font-weight="700"
          :fill="mono.MUTED"
        >
          {{ r.text }}
        </text>

        <!-- 月份：上檐小字 + 钉住自己那一列的小竖线 -->
        <g v-for="m in monthMarks" :key="m.key">
          <text
            class="ch-month"
            :x="m.x + geo.pitch / 2"
            :y="geo.y0 - 8"
            text-anchor="middle"
            font-size="7"
            font-weight="700"
            letter-spacing="0.08em"
            :fill="mono.MUTED"
          >
            {{ m.text }}
          </text>
          <line
            class="ch-monthline"
            :x1="m.x + geo.pitch / 2"
            :y1="geo.y0 - 4"
            :x2="m.x + geo.pitch / 2"
            :y2="geo.y0 + 1"
            :stroke="mono.FAINT"
            stroke-width="0.7"
          />
        </g>

        <!-- 一天一个点：面积 = 当天量，明度 = 分位档 -->
        <circle
          v-for="d in dots"
          :key="d.key"
          class="ch-dot"
          :cx="d.cx"
          :cy="d.cy"
          :r="d.r"
          :fill="d.shade"
          :style="{ animationDelay: `${d.delay}ms` }"
        >
          <title>{{ d.readout }}</title>
        </circle>

        <!-- 全年峰值：虚线圈（第二编码，不靠明度抢视线） -->
        <circle
          v-if="peakDot"
          class="ch-peak"
          :cx="peakDot.cx"
          :cy="peakDot.cy"
          :r="peakDot.r + 3.4"
          fill="none"
          :stroke="mono.INK"
          stroke-width="1"
          stroke-dasharray="2 3"
          :style="{ animationDelay: '900ms' }"
        />
      </g>
    </svg>

    <p class="ch-foot">
      <span class="ch-key">明度 {{ mono.LAD.length }} 档（按分位切）</span>
      <span v-for="b in legend" :key="b.text" class="ch-band">
        <i :style="{ background: b.color }" aria-hidden="true" />{{ b.text }}
      </span>
      {{ footNote }}
    </p>
  </div>
</template>

<style scoped>
.ch-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88; /* mono.MUTED */
  font-size: 12.5px;
}
.ch {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.ch-svg {
  display: block;
  flex: 1 1 auto;
  min-height: 0;
}
.ch-g {
  opacity: 0;
}
.ch-g--in {
  opacity: 1;
}
.ch-dot,
.ch-peak,
.ch-row,
.ch-month,
.ch-monthline {
  transform-box: fill-box;
  transform-origin: center;
  animation: ch-in 0.5s cubic-bezier(0.2, 0.7, 0.3, 1.2) both;
}
@keyframes ch-in {
  from {
    opacity: 0;
    transform: scale(0.2);
  }
}
.ch-foot {
  margin: 4px 0 0;
  font-size: 10px;
  color: #8f8e88; /* mono.MUTED */
  line-height: 1.7;
}
.ch-key {
  margin-right: 6px;
}
.ch-band {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-right: 8px;
  color: #6a6963; /* mono.L[2] */
  font-variant-numeric: tabular-nums;
}
.ch-band i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
@media (prefers-reduced-motion: reduce) {
  .ch-g {
    opacity: 1;
  }
  .ch-dot,
  .ch-peak,
  .ch-row,
  .ch-month,
  .ch-monthline {
    animation: none;
  }
}
</style>
