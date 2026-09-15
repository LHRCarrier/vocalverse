<script setup lang="ts">
/**
 * **F4 Tick Donut** — lieflat Basics 组（`catalog.md`：100% 构成 ≤6 段 · SVG）。
 * 结构正本：`templates/basics-gallery.html` · 卡内标题 `Where the traffic comes from`
 * （渲染代码块 `// ════ B4 · tick donut ════`，副标题 `one tick = one percent ... read it like a clock`）。
 *
 * 从该卡搬过来的结构：
 * - **1 格 = 1%**：整圈 100 根刻度，起点在 12 点方向、顺时针读数（模板脚注
 *   `TWELVE O'CLOCK IS ZERO · READS CLOCKWISE`）；
 * - **段间留一格呼吸**：每段第一根刻度让位，段与段不糊成一片；
 * - **每 10 格一个点标**（内圈小点），给出"读钟"的节拍；
 * - 段标签在弧外、用虚线引线牵回弧上，`text-anchor` 按中角余弦切换；
 * - 圆心只放总占比与口径（模板 `100` + `TICKS · ONE = 1%`）。
 *
 * 契约要求的 `sect()`：段本身画成**环形扇区带**（`sect(cx,cy,rIn,rOut,a0,a1)`），
 * 刻度立在带上——不是饼图（Mono 对饼图的默认替换就是 tick donut）。
 * 明度即数据：段按数值降序沿 `mono.L` 阶梯从黑到浅分配，长尾合并为"其他"（段数 ≤6）。
 * 段标签用 `mono.L[1]` 而不是段自身明度：`L[4]/L[5]` 在纸底上对比度不足，
 * 小字读不出来（仍在 ladder 内，颜色没有出圈）；段与标签的对应靠角度 + 同色引线。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { mono, pol, rnd, sect } from './mono'

export interface DonutItem {
  label: string
  value: number
}

const props = withDefaults(
  defineProps<{
    items: DonutItem[]
    unit?: string
    /** 圆心下方口径说明（默认给"共 N 个单位"） */
    centerLabel?: string
    revealed?: boolean
  }>(),
  { unit: '', centerLabel: '', revealed: true },
)

/** 段数上限：超出就把长尾并成"其他" */
const MAX_SEG = 6
/** 整圈刻度数 = 100（1 格 = 1%） */
const TICKS = 100
const DEG_PER_TICK = 360 / TICKS

const host = ref<HTMLElement | null>(null)
const box = ref({ w: 380, h: 240 })
let ro: ResizeObserver | null = null

onMounted(() => {
  const node = host.value
  if (!node) return
  const read = (): void => {
    box.value = { w: Math.max(180, node.clientWidth), h: Math.max(140, node.clientHeight) }
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

const segmentsIn = computed(() => {
  const clean = props.items.filter((it) => Number.isFinite(it.value) && it.value > 0)
  const sorted = [...clean].sort((a, b) => b.value - a.value)
  if (sorted.length <= MAX_SEG) return sorted
  const head = sorted.slice(0, MAX_SEG - 1)
  const tail = sorted.slice(MAX_SEG - 1).reduce((sum, it) => sum + it.value, 0)
  return [...head, { label: '其他', value: tail }]
})

const total = computed(() => segmentsIn.value.reduce((sum, it) => sum + it.value, 0))
const hasData = computed(() => total.value > 0)

const geo = computed(() => {
  const { w, h } = box.value
  const cx = w / 2
  const cy = h / 2 + 6
  const rOut = Math.max(22, Math.min(w / 2 - 56, h / 2 - 28))
  return { w, h, cx, cy, rIn: Math.max(12, rOut - 14), rOut, rLabel: rOut + 30 }
})

interface Tick {
  x1: number
  y1: number
  x2: number
  y2: number
  /** 内圈点标位置（每 10 格一个） */
  dotX: number
  dotY: number
  dot: boolean
}

interface Seg {
  label: string
  value: number
  pct: number
  shade: string
  /** 环形扇区带（sect）：段的"底色" */
  band: string
  ticks: Tick[]
  /** 引线：弧 → 标签 */
  leader: { x1: number; y1: number; x2: number; y2: number }
  anchor: 'start' | 'middle' | 'end'
  lx: number
  ly: number
  readout: string
  delay: number
}

function ticksFor(start: number, end: number, si: number, rIn: number, rOut: number, cx: number, cy: number): Tick[] {
  const out: Tick[] = []
  for (let k = start; k < end; k += 1) {
    // 段间呼吸：非首段的头一根刻度让位
    if (si > 0 && k === start) continue
    const a = -90 + (k + 0.5) * DEG_PER_TICK
    const len = 8 + rnd(k + 1, si + 2) * 6
    const [x1, y1] = pol(cx, cy, rOut, a)
    const [x2, y2] = pol(cx, cy, rOut + len, a)
    const [dotX, dotY] = pol(cx, cy, rIn - 5, a)
    out.push({ x1, y1, x2, y2, dotX, dotY, dot: k > 0 && k % 10 === 0 })
  }
  return out
}

const segs = computed<Seg[]>(() => {
  if (!hasData.value) return []
  const g = geo.value
  let cum = 0
  return segmentsIn.value.map((it, si) => {
    const start = Math.round(cum)
    cum += (it.value / total.value) * TICKS
    const end = Math.max(start + 1, Math.round(cum))
    const a0 = -90 + start * DEG_PER_TICK
    const a1 = -90 + end * DEG_PER_TICK
    const gap = segmentsIn.value.length > 1 ? 0.9 : 0
    const shade = mono.L[Math.min(si, mono.L.length - 1)]
    const mid = (a0 + a1) / 2
    const cos = Math.cos((mid * Math.PI) / 180)
    const [lx, ly] = pol(g.cx, g.cy, g.rLabel, mid)
    const [gx, gy] = pol(g.cx, g.cy, g.rOut + 18, mid)
    return {
      label: it.label,
      value: it.value,
      pct: (it.value / total.value) * 100,
      shade,
      band: sect(g.cx, g.cy, g.rIn, g.rOut, a0 + gap, Math.max(a0 + gap + 0.5, a1 - gap)),
      ticks: ticksFor(start, end, si, g.rIn, g.rOut, g.cx, g.cy),
      leader: { x1: gx, y1: gy, x2: lx, y2: ly },
      anchor: cos > 0.3 ? 'start' : cos < -0.3 ? 'end' : 'middle',
      lx,
      ly,
      readout: `${it.label} — ${Math.round((it.value / total.value) * 100)}%（${fmt(it.value)}${props.unit}）`,
      delay: 600 + si * 100,
    }
  })
})

const centerNote = computed(
  () => props.centerLabel || `共 ${fmt(total.value)}${props.unit || ' 个单位'}`,
)
function fmt(v: number): number | string {
  return Number.isInteger(v) ? v : Math.round(v * 100) / 100
}
</script>

<template>
  <div v-if="!hasData" class="td-empty">暂无数据（没有可分解的构成）</div>
  <div v-else ref="host" class="td">
    <svg
      class="td-svg"
      :width="geo.w"
      :height="geo.h"
      :viewBox="`0 0 ${geo.w} ${geo.h}`"
      role="img"
      :aria-label="`环形构成图，${segs.length} 段：${segs.map((s) => `${s.label} ${Math.round(s.pct)}%`).join('、')}`"
    >
      <g class="td-g" :class="{ 'td-g--in': revealed }">
        <!-- 段带（sect 环形扇区） -->
        <path v-for="(s, si) in segs" :key="`band-${si}`" class="td-band" :d="s.band" :fill="s.shade">
          <title>{{ s.readout }}</title>
        </path>

        <!-- 刻度：1 格 = 1% -->
        <g v-for="(s, si) in segs" :key="`tk-${si}`">
          <line
            v-for="(t, k) in s.ticks"
            :key="`t-${si}-${k}`"
            class="td-tick"
            :x1="t.x1"
            :y1="t.y1"
            :x2="t.x2"
            :y2="t.y2"
            :stroke="s.shade"
            stroke-width="1"
            :style="{ animationDelay: `${(si * 8 + k) * mono.MOTION.staggerDot}ms` }"
          />
          <!-- 内圈点标：每 10 格一个，给"读钟"的节拍 -->
          <circle
            v-for="(t, k) in s.ticks.filter((x) => x.dot)"
            :key="`d-${si}-${k}`"
            class="td-dot"
            :cx="t.dotX"
            :cy="t.dotY"
            r="0.9"
            :fill="mono.L[4]"
            :style="{ animationDelay: `${600 + k * 10}ms` }"
          />
        </g>

        <!-- 段外标签 + 虚线引线 -->
        <g v-for="(s, si) in segs" :key="`lb-${si}`">
          <line
            class="td-lead"
            :x1="s.leader.x1"
            :y1="s.leader.y1"
            :x2="s.leader.x2"
            :y2="s.leader.y2"
            :stroke="s.shade"
            stroke-width="0.7"
            stroke-dasharray="1 3"
            :style="{ animationDelay: `${s.delay}ms` }"
          />
          <text
            class="td-label"
            :x="s.lx"
            :y="s.ly + 3"
            :text-anchor="s.anchor"
            font-size="8.5"
            font-weight="800"
            letter-spacing="0.04em"
            :fill="mono.L[1]"
            :style="{ animationDelay: `${s.delay + 40}ms` }"
          >
            {{ s.label }} · {{ Math.round(s.pct) }}%
          </text>
        </g>

        <!-- 圆心：总占比 + 口径 -->
        <text
          class="td-center"
          :x="geo.cx"
          :y="geo.cy + 2"
          text-anchor="middle"
          font-size="22"
          font-weight="800"
          :fill="mono.INK"
          :style="{ animationDelay: '900ms' }"
        >
          100<tspan font-size="11" :fill="mono.MUTED">%</tspan>
        </text>
        <text
          class="td-center-note"
          :x="geo.cx"
          :y="geo.cy + 18"
          text-anchor="middle"
          font-size="7"
          font-weight="600"
          letter-spacing="0.1em"
          :fill="mono.MUTED"
          :style="{ animationDelay: '950ms' }"
        >
          {{ centerNote }}
        </text>
      </g>
    </svg>

    <p class="td-foot">1 格 = 1% · 12 点方向为 0 · 顺时针读 · 每 10 格一个点标</p>
  </div>
</template>

<style scoped>
.td-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88; /* mono.MUTED */
  font-size: 12.5px;
}
.td {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.td-svg {
  display: block;
  flex: 1 1 auto;
  min-height: 0;
  overflow: visible;
}
.td-g {
  opacity: 0;
}
.td-g--in {
  opacity: 1;
}
.td-band,
.td-tick,
.td-dot,
.td-lead,
.td-label,
.td-center,
.td-center-note {
  animation: td-in 0.7s cubic-bezier(0.25, 1, 0.5, 1) both;
}
@keyframes td-in {
  from {
    opacity: 0;
  }
}
.td-foot {
  margin: 4px 0 0;
  font-size: 10px;
  color: #8f8e88; /* mono.MUTED */
  font-variant-numeric: tabular-nums;
}
@media (prefers-reduced-motion: reduce) {
  .td-g {
    opacity: 1;
  }
  .td-band,
  .td-tick,
  .td-dot,
  .td-lead,
  .td-label,
  .td-center,
  .td-center-note {
    animation: none;
  }
}
</style>
