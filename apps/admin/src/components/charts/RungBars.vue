<script setup lang="ts">
/**
 * **F1 Rung Bars** — lieflat Basics 组（`catalog.md`：少类目比较 ≤8 · 单位可数 · SVG）。
 * 结构正本：`templates/basics-gallery.html` · 卡内标题 `Revenue by plan, rung by rung`
 * （渲染代码块 `// ════ B1 · rung bars ════`，副标题 `one rung = one $k of MRR`）。
 *
 * 从该卡搬过来的结构（不是"另画一张差不多的柱状图"）：
 * - **梯级柱**：柱身不是一根实心棒，而是**一格格横档**，1 格 = 1 个诚实单位
 *   （模板里 `one rung = one $k`，这里 = 1 个 `unit`）。段数 = 取整后的单位数，
 *   段宽/明度按 `rnd(k,i)` 微抖，近看每一格都数得出来；
 * - **每 5 格一个点标**（模板原话 `DOT MARKS EVERY FIFTH`）：让"数格子"有节奏，
 *   不用逐格描线也能一眼估读；
 * - **柱端胶囊只圆上端**（`capsuleBarTop`，SKILL §2「竖柱圆上端」）；
 * - **长度 ∝ 数值、绝不断轴**：`h = value / max * hMax`，没有任何下限压缩；
 *   唯一退化是**单位过密**（最大值 > 60 格，格子细到 < 1.4px）时退化为实心柱，
 *   此时在脚注里明说"仅示长度"——退化的是格子，不是长度；
 * - 柱顶数值 + 柱脚类目名 + 底线（家具层），与模板同序。
 *
 * 为什么用 `ResizeObserver` 真像素而不是 `preserveAspectRatio="none"`：
 * 胶囊圆角与点标是圆，非等比拉伸会把它们压成椭圆（`HairlineLine` 里同样的理由
 * 让它把刻度画成竖线而不是圆点）。真像素下文字也不必搬去外层 HTML。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { capsuleBarTop, mono, rnd, staggerDelay } from './mono'

export interface RungItem {
  label: string
  value: number
}

const props = withDefaults(
  defineProps<{
    items: RungItem[]
    unit?: string
    formatValue?: (v: number) => string
    revealed?: boolean
  }>(),
  {
    unit: '',
    revealed: true,
    formatValue: (v: number) => String(Math.round(v * 100) / 100),
  },
)

/** 上下留白：上给柱顶数值，下给类目名 */
const PAD_T = 24
const PAD_B = 22
const PAD_X = 10
/** 单格最小可辨高度（px）：细到这个数以下就退化 */
const MIN_SEG = 1.4
/** 段数上限（契约：> 60 退化为实心柱） */
const MAX_RUNGS = 60

const host = ref<HTMLElement | null>(null)
const box = ref({ w: 360, h: 220 })
let ro: ResizeObserver | null = null

onMounted(() => {
  const node = host.value
  if (!node) return
  const read = (): void => {
    box.value = { w: Math.max(120, node.clientWidth), h: Math.max(90, node.clientHeight) }
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

/** 只保留有限数值：`NaN`/`Infinity` 画出来是"看着有值"的假柱 */
const clean = computed(() => props.items.filter((it) => Number.isFinite(it.value)))
const max = computed(() => Math.max(0, ...clean.value.map((it) => it.value)))
const hasData = computed(() => clean.value.length > 0 && max.value > 0)
/** 段数 = 取整后的单位数；过密则退化 */
const runged = computed(() => max.value <= MAX_RUNGS)

interface Rung {
  /** 非顶格用矩形；顶格用胶囊路径（只圆上端） */
  path: string
  x: number
  y: number
  w: number
  h: number
  top: boolean
  opacity: number
  delay: number
  /** 每 5 格的点标 */
  dot: boolean
}

interface Bar {
  label: string
  value: number
  cx: number
  slotX: number
  /** 柱顶 y（放数值） */
  topY: number
  rungs: Rung[]
  readout: string
}

const geo = computed(() => {
  const { w, h } = box.value
  const innerW = Math.max(40, w - PAD_X * 2)
  const innerH = Math.max(40, h - PAD_T - PAD_B)
  const slot = innerW / Math.max(clean.value.length, 1)
  return { w, h, innerW, innerH, slot, baseY: h - PAD_B }
})

/** 一格 = 一个单位：段数取整（四舍五入，与模板"数格子"的口径一致） */
function buildRungs(count: number, full: number, cx: number, barW: number, baseY: number, i: number): Rung[] {
  const segH = full / count
  const gap = Math.min(1.35, segH * 0.32)
  const out: Rung[] = []
  for (let k = 0; k < count; k += 1) {
    const shrink = 0.9 + rnd(k + 1, i + 2) * 0.14
    const w = Math.max(3, barW * shrink)
    const x = cx - w / 2
    const y = baseY - (k + 1) * segH
    const h = Math.max(0.8, segH - gap)
    const top = k === count - 1
    out.push({
      path: top ? capsuleBarTop(x, y + gap / 2, w, h) : '',
      x,
      y: y + gap / 2,
      w,
      h,
      top,
      opacity: 0.55 + rnd(k + 2, i + 4) * 0.45,
      delay: i * mono.MOTION.staggerBar + k * mono.MOTION.staggerDot,
      dot: k % 5 === 4,
    })
  }
  return out
}

const bars = computed<Bar[]>(() => {
  if (!hasData.value) return []
  const g = geo.value
  const mx = max.value
  const barW = Math.min(38, Math.max(9, g.slot * 0.46))
  return clean.value.map((it, i) => {
    const cx = PAD_X + g.slot * (i + 0.5)
    const full = (it.value / mx) * g.innerH
    const count = runged.value ? Math.max(1, Math.round(it.value)) : 1
    return {
      label: it.label,
      value: it.value,
      cx,
      slotX: PAD_X + g.slot * i,
      topY: g.baseY - full,
      rungs: buildRungs(count, full, cx, barW, g.baseY, i),
      readout: `${it.label} — ${props.formatValue(it.value)}${props.unit}`,
    }
  })
})

const peakIndex = computed(() => clean.value.findIndex((it) => it.value === max.value))
const footNote = computed(() => {
  if (!hasData.value) return ''
  if (!runged.value) return `单位过密（最大 ${max.value} 格，格子细于 ${MIN_SEG}px），仅示长度`
  return `1 格 = 1 ${props.unit || '个单位'} · 每 5 格一个点标`
})
const delayOf = (i: number, k: number): number => staggerDelay(i, 'bar') + staggerDelay(k, 'dot')
</script>

<template>
  <div v-if="!hasData" class="rb-empty">暂无数据（没有可比较的类目）</div>
  <div v-else ref="host" class="rb">
    <svg
      class="rb-svg"
      :width="geo.w"
      :height="geo.h"
      :viewBox="`0 0 ${geo.w} ${geo.h}`"
      role="img"
      :aria-label="`梯级柱状图，${bars.length} 个类目，最高 ${formatValue(max)}${unit}`"
    >
      <!-- 家具层：底线告诉读者"0 在哪" -->
      <line
        :x1="PAD_X - 2"
        :x2="geo.w - PAD_X + 2"
        :y1="geo.baseY"
        :y2="geo.baseY"
        :stroke="mono.GRID"
        stroke-width="0.8"
      />

      <g class="rb-g" :class="{ 'rb-g--in': revealed }">
        <g v-for="(bar, i) in bars" :key="bar.label">
          <template v-for="(r, k) in bar.rungs" :key="`${bar.label}-r-${k}`">
            <rect
              v-if="!r.top"
              class="rb-rung"
              :x="r.x"
              :y="r.y"
              :width="r.w"
              :height="r.h"
              rx="0.8"
              :fill="mono.L[0]"
              :style="{ opacity: r.opacity, animationDelay: `${r.delay}ms` }"
            />
            <path
              v-else
              class="rb-rung"
              :d="r.path"
              :fill="mono.L[0]"
              :style="{ opacity: r.opacity, animationDelay: `${r.delay}ms` }"
            />
            <circle
              v-if="r.dot"
              class="rb-dot"
              :cx="bar.cx + r.w / 2 + 4.2"
              :cy="r.y + r.h / 2"
              r="0.9"
              :fill="mono.FAINT"
              :style="{ animationDelay: `${r.delay}ms` }"
            />
          </template>

          <text
            class="rb-num"
            :x="bar.cx"
            :y="bar.topY - 7"
            text-anchor="middle"
            :font-size="10"
            font-weight="800"
            :fill="mono.INK"
            :style="{ animationDelay: `${delayOf(i, 0) + 240}ms` }"
          >
            {{ formatValue(bar.value) }}<tspan v-if="unit" :font-size="7.5" :fill="mono.MUTED">{{ unit }}</tspan>
          </text>

          <text
            class="rb-lab"
            :x="bar.cx"
            :y="geo.baseY + 13"
            text-anchor="middle"
            :font-size="7.5"
            font-weight="700"
            letter-spacing="0.06em"
            :fill="mono.MUTED"
            :style="{ animationDelay: `${delayOf(i, 0)}ms` }"
          >
            {{ bar.label }}
          </text>

          <!-- 命中区：整格宽，原生 title 出读数（零 JS） -->
          <rect
            :x="bar.slotX"
            y="0"
            :width="geo.slot"
            :height="geo.h"
            fill="transparent"
          >
            <title>{{ bar.readout }}{{ i === peakIndex ? '　（最高）' : '' }}</title>
          </rect>
        </g>
      </g>
    </svg>

    <p class="rb-foot">{{ footNote }}</p>
  </div>
</template>

<style scoped>
.rb-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88; /* mono.MUTED */
  font-size: 12.5px;
}
.rb {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.rb-svg {
  display: block;
  flex: 1 1 auto;
  min-height: 0;
}
.rb-g {
  opacity: 0;
}
.rb-g--in {
  opacity: 1;
}
.rb-rung,
.rb-dot,
.rb-num,
.rb-lab {
  animation: rb-rise 0.9s cubic-bezier(0.25, 1, 0.5, 1) both;
}
/* 从下往上浮起：柱是"长出来"的，不是"淡出来"的 */
@keyframes rb-rise {
  from {
    opacity: 0;
    transform: translateY(5px);
  }
}
.rb-foot {
  margin: 4px 0 0;
  font-size: 10px;
  color: #8f8e88; /* mono.MUTED */
  font-variant-numeric: tabular-nums;
}
@media (prefers-reduced-motion: reduce) {
  .rb-g {
    opacity: 1;
  }
  .rb-rung,
  .rb-dot,
  .rb-num,
  .rb-lab {
    animation: none;
  }
}
</style>
