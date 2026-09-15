<script setup lang="ts">
/**
 * **F5 Tick Rows** — lieflat Basics 组（`catalog.md`：横向排名比较 · 单位可数 ≤8 行 · SVG）。
 * 结构正本：`templates/basics-gallery.html` · 卡内标题 `Six teams, shipped and counted`
 * （渲染代码块 `// ════ C1 · tick rows ════`，副标题 `the row is a queue, not a bar`）。
 *
 * 从该卡搬过来的结构：
 * - **一行 = 一支队列**：每行一条浅色轨道（轨道全长 = 同一口径的满量），
 *   轨道上**一格 = 一个单位**，格子从轨道往上长，高矮/明度按 `rnd(k,i)` 微抖；
 * - **每 5 格一个点标**（模板脚注 `DOT MARKS EVERY FIFTH`），左侧类目名、行尾大数；
 * - **长度 ∝ 数值，绝不断轴**：格子间距取自"满量"而不是"最大值"，
 *   所以"最大值行"到轨尾还留得下空位——这是排名图诚实的地方（看得出离满量还有多远）。
 *   若传入的 `max` 小于实际最大值，则按实际最大值放大轨道（宁可冲出去，也不截断）；
 * - 行内不画坐标轴、不画网格：模板的横轴就是"轨道本身"。
 *
 * 退化规则（并在脚注里明说）：格子细到 2.4px 以下时改用**实心胶囊横柱**（`capsuleBarRight`），
 * 长度编码不变，只是不再逐格可数。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { capsuleBarRight, mono, rnd } from './mono'

export interface TickRowItem {
  label: string
  value: number
}

const props = withDefaults(
  defineProps<{
    items: TickRowItem[]
    unit?: string
    /** 轨道满量（同一把尺子）；缺省 = 数据最大值 */
    max?: number
    revealed?: boolean
  }>(),
  { unit: '', max: 0, revealed: true },
)

/** 单格最小可辨间距（px） */
const MIN_TICK = 2.4
const PAD_T = 6
const PAD_B = 4

const host = ref<HTMLElement | null>(null)
const box = ref({ w: 380, h: 220 })
let ro: ResizeObserver | null = null

onMounted(() => {
  const node = host.value
  if (!node) return
  const read = (): void => {
    box.value = { w: Math.max(180, node.clientWidth), h: Math.max(80, node.clientHeight) }
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

const clean = computed(() => props.items.filter((it) => Number.isFinite(it.value) && it.value > 0))
const maxValue = computed(() => (clean.value.length ? Math.max(...clean.value.map((it) => it.value)) : 0))
/** 轨道满量：显式 max 与实际最大值取大 → 只会"冲出去"，绝不会把值截到轴外 */
const domain = computed(() => Math.max(props.max > 0 ? props.max : 0, maxValue.value))
const hasData = computed(() => clean.value.length > 0 && domain.value > 0)

const geo = computed(() => {
  const { w, h } = box.value
  const rows = Math.max(clean.value.length, 1)
  const labelW = Math.min(112, Math.max(56, w * 0.3))
  const valueW = 46
  const trackW = Math.max(40, w - labelW - valueW)
  const rowH = Math.max(14, (h - PAD_T - PAD_B) / rows)
  const px = trackW / domain.value
  return { w, h, labelW, trackW, rowH, px, x0: labelW, solid: px < MIN_TICK }
})

interface Tick {
  x: number
  y1: number
  y2: number
  opacity: number
  dot: boolean
}

interface Row {
  label: string
  value: number
  /** 行内纵向中心 */
  cy: number
  trackY: number
  ticks: Tick[]
  /** 实心退化时的横柱路径 */
  solidPath: string
  solidW: number
  valueX: number
  valueY: number
  readout: string
  delay: number
}

function buildTicks(count: number, i: number, y: number, h: number, x0: number, px: number): Tick[] {
  const out: Tick[] = []
  for (let k = 0; k < count; k += 1) {
    const x = x0 + k * px + px / 2
    const th = h * (0.72 + rnd(k + 1, i + 2) * 0.28)
    out.push({ x, y1: y, y2: y - th, opacity: 0.55 + rnd(k + 3, i + 5) * 0.45, dot: k % 5 === 4 })
  }
  return out
}

const rows = computed<Row[]>(() => {
  if (!hasData.value) return []
  const g = geo.value
  const tickH = Math.min(15, Math.max(7, g.rowH * 0.36))
  return clean.value.map((it, i) => {
    const cy = PAD_T + g.rowH * (i + 0.5)
    const trackY = cy + tickH / 2 - 1
    const count = Math.max(1, Math.round(it.value))
    const w = Math.max(2, it.value * g.px)
    return {
      label: it.label,
      value: it.value,
      cy,
      trackY,
      ticks: g.solid ? [] : buildTicks(count, i, trackY, tickH, g.x0, g.px),
      solidPath: g.solid ? capsuleBarRight(g.x0, cy - tickH / 2, w, tickH) : '',
      solidW: w,
      valueX: g.x0 + w + 9,
      valueY: cy - tickH / 2 + tickH * 0.5 + 3.5,
      readout:
        `${it.label} — ${it.value}${props.unit}` +
        (props.max > 0 ? `（满量 ${props.max}${props.unit}）` : ''),
      delay: i * mono.MOTION.staggerBar,
    }
  })
})

const footNote = computed(() => {
  if (!hasData.value) return ''
  const base = `1 格 = 1 个单位 · 每 5 格一个点标 · 轨道全长 = ${domain.value}${props.unit}`
  return geo.value.solid ? `${base}（单位过密，已退化为实心柱：仅示长度，不再逐格可数）` : base
})
</script>

<template>
  <div v-if="!hasData" class="tr-empty">暂无数据（没有可排名的行）</div>
  <div v-else ref="host" class="tr">
    <svg
      class="tr-svg"
      :width="geo.w"
      :height="geo.h"
      :viewBox="`0 0 ${geo.w} ${geo.h}`"
      role="img"
      :aria-label="`横向排名图，${rows.length} 行，最高 ${maxValue}${unit}`"
    >
      <g class="tr-g" :class="{ 'tr-g--in': revealed }">
        <g v-for="row in rows" :key="row.label">
          <!-- 类目列 -->
          <text
            class="tr-lab"
            :x="geo.x0 - 10"
            :y="row.cy + 3"
            text-anchor="end"
            font-size="8"
            font-weight="700"
            letter-spacing="0.06em"
            :fill="mono.L[2]"
            :style="{ animationDelay: `${row.delay}ms` }"
          >
            {{ row.label }}
          </text>

          <!-- 轨道：全长 = 满量（"离满量还差多少"本身是信息） -->
          <line
            class="tr-track"
            :x1="geo.x0"
            :y1="row.trackY"
            :x2="geo.x0 + geo.trackW"
            :y2="row.trackY"
            :stroke="mono.GRID"
            stroke-width="0.6"
            :style="{ animationDelay: `${row.delay}ms` }"
          />

          <template v-if="row.ticks.length">
            <template v-for="(t, k) in row.ticks" :key="`${row.label}-${k}`">
              <line
                class="tr-tick"
                :x1="t.x"
                :x2="t.x"
                :y1="t.y1"
                :y2="t.y2"
                :stroke="mono.L[0]"
                stroke-width="0.9"
                :opacity="t.opacity"
                :style="{ animationDelay: `${row.delay + k * mono.MOTION.staggerDot}ms` }"
              />
              <circle
                v-if="t.dot"
                class="tr-dot"
                :cx="t.x"
                :cy="t.y1 + 4"
                r="0.85"
                :fill="mono.FAINT"
                :style="{ animationDelay: `${row.delay + k * mono.MOTION.staggerDot}ms` }"
              />
            </template>
          </template>
          <path
            v-else
            class="tr-solid"
            :d="row.solidPath"
            :fill="mono.L[0]"
            :style="{ animationDelay: `${row.delay}ms` }"
          />

          <!-- 行尾大数 -->
          <text
            class="tr-num"
            :x="row.valueX"
            :y="row.valueY"
            font-size="10.5"
            font-weight="800"
            :fill="mono.INK"
            :style="{ animationDelay: `${row.delay + 260}ms` }"
          >
            {{ row.value }}<tspan v-if="unit" font-size="7.5" :fill="mono.MUTED">{{ unit }}</tspan>
          </text>

          <!-- 命中区：整行，原生 title 出读数 -->
          <rect
            :x="0"
            :y="row.cy - geo.rowH / 2"
            :width="geo.w"
            :height="geo.rowH"
            fill="transparent"
          >
            <title>{{ row.readout }}</title>
          </rect>
        </g>
      </g>
    </svg>

    <p class="tr-foot">{{ footNote }}</p>
  </div>
</template>

<style scoped>
.tr-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88; /* mono.MUTED */
  font-size: 12.5px;
}
.tr {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.tr-svg {
  display: block;
  flex: 1 1 auto;
  min-height: 0;
}
.tr-g {
  opacity: 0;
}
.tr-g--in {
  opacity: 1;
}
.tr-tick,
.tr-dot,
.tr-lab,
.tr-num,
.tr-track,
.tr-solid {
  animation: tr-in 0.7s cubic-bezier(0.25, 1, 0.5, 1) both;
}
@keyframes tr-in {
  from {
    opacity: 0;
    transform: translateX(-4px);
  }
}
.tr-foot {
  margin: 4px 0 0;
  font-size: 10px;
  color: #8f8e88; /* mono.MUTED */
  font-variant-numeric: tabular-nums;
}
@media (prefers-reduced-motion: reduce) {
  .tr-g {
    opacity: 1;
  }
  .tr-tick,
  .tr-dot,
  .tr-lab,
  .tr-num,
  .tr-track,
  .tr-solid {
    animation: none;
  }
}
</style>
