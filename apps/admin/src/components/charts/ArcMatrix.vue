<script setup lang="ts">
/**
 * **L4 Arc Matrix** — lieflat Lupi 编辑型（`catalog.md`：分类×分类+量 · 小数据 ≤100 格 · SVG）。
 * 结构正本：`templates/lupi-gallery.html` · 卡内标题 `Eight products land in twelve cities`
 * （渲染代码块 `// ════ 3 · arc bubble matrix ════`，副标题 `bubble = paying accounts · each row bows like a horizon`）。
 *
 * 从该卡搬过来的结构：
 * - **每行弯成一条地平线**（模板 `dy(j) = -16·sin(π·j/(cols-1))`）：
 *   行与行之间因此不会连成一张"表格网"，读者的眼睛跟着弧线走一行，再跳下一行；
 * - **行名在左、列名在斜上**（模板 `rotate(-55)`），矩阵结构（谁×谁）明确画出来，
 *   不退化成一堆没有坐标的点；
 * - **静默格留一粒极小点**（模板 `a few true absences` → 小点而不是空格），
 *   "这个城市没有这个产品"和"这里没画"是两回事；
 * - 最亮的几格直接标数（模板取全局 top-4）。
 *
 * 与模板有意不同的一点（契约硬约束）：模板用**气泡面积**编码（`sqrt(v)*1.3` 半径），
 * 这里用**圆角方块 + 明度档位**——L4 是"轻量矩阵"，格子对齐成矩阵才好横向比较，
 * 而且契约要求"格子明度 = 数值档位、重点格（该行最大）加一圈 0.7px 描边"。
 * 明度档用分位切（`./bands`），数据偏斜时不会把九成格子压进一档。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { bandLegend, quantileBands, shadeOfBand } from './bands'
import { mono } from './mono'

const props = withDefaults(
  defineProps<{
    rows: string[]
    cols: string[]
    matrix: number[][]
    unit?: string
    revealed?: boolean
  }>(),
  { unit: '', revealed: true },
)

/** L4 的容量上限：超过就不是"轻量矩阵"了 */
const MAX_CELLS = 100
const PAD_T = 30
const PAD_B = 20
const PAD_R = 8
/** 列名倾斜角（模板 -55°） */
const TILT = -55

const host = ref<HTMLElement | null>(null)
const box = ref({ w: 430, h: 260 })
let ro: ResizeObserver | null = null

onMounted(() => {
  const node = host.value
  if (!node) return
  const read = (): void => {
    box.value = { w: Math.max(200, node.clientWidth), h: Math.max(120, node.clientHeight) }
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

const valueAt = (i: number, j: number): number => {
  const v = props.matrix[i]?.[j]
  return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : 0
}

const shapeOk = computed(() => props.rows.length > 0 && props.cols.length > 0)
const max = computed(() => {
  let m = 0
  for (let i = 0; i < props.rows.length; i += 1) {
    for (let j = 0; j < props.cols.length; j += 1) m = Math.max(m, valueAt(i, j))
  }
  return m
})
const hasData = computed(() => shapeOk.value && max.value > 0)
const cellCount = computed(() => props.rows.length * props.cols.length)

const thresholds = computed(() => {
  const pool: number[] = []
  for (let i = 0; i < props.rows.length; i += 1) {
    for (let j = 0; j < props.cols.length; j += 1) {
      const v = valueAt(i, j)
      if (v > 0) pool.push(v)
    }
  }
  return quantileBands(pool)
})

/** 每行的最大值（重点格：加 0.7px 描边） */
const rowMax = computed(() => props.rows.map((_, i) => {
  let m = 0
  for (let j = 0; j < props.cols.length; j += 1) m = Math.max(m, valueAt(i, j))
  return m
}))
/** 全局 top-4：直接标数（模板只标最亮的几格，避免 96 个数字糊满整卡） */
const labelled = computed(() => {
  const all: { v: number; key: string }[] = []
  for (let i = 0; i < props.rows.length; i += 1) {
    for (let j = 0; j < props.cols.length; j += 1) all.push({ v: valueAt(i, j), key: `${i}-${j}` })
  }
  return new Set(all.sort((a, b) => b.v - a.v).slice(0, 4).filter((d) => d.v > 0).map((d) => d.key))
})

const geo = computed(() => {
  const { w, h } = box.value
  const labelW = Math.min(w * 0.28, Math.max(...props.rows.map((r) => r.length), 1) * 7 + 12)
  const innerW = Math.max(50, w - labelW - PAD_R)
  const innerH = Math.max(50, h - PAD_T - PAD_B)
  const cellW = innerW / Math.max(props.cols.length, 1)
  const cellH = innerH / Math.max(props.rows.length, 1)
  const cs = Math.max(5, Math.min(15, cellW * 0.6, cellH * 0.6))
  return {
    w,
    h,
    labelW,
    innerW,
    cellW,
    cellH,
    cs,
    x0: labelW,
    y0: PAD_T,
    /** 地平线拱高：行内两端的格比中间低，弯成一条弧 */
    amp: Math.min(13, cellH * 0.42),
  }
})

/** 拱形偏移（列方向）：两端下沉、中间抬起 */
const bowY = (j: number, cols: number, amp: number): number => {
  if (cols < 3) return 0
  return -amp * Math.sin((Math.PI * j) / (cols - 1))
}

interface Cell {
  key: string
  cx: number
  cy: number
  size: number
  shade: string
  quiet: boolean
  key3: boolean
  label: string | null
  labelY: number
  readout: string
  delay: number
}

const cells = computed<Cell[]>(() => {
  if (!hasData.value) return []
  const g = geo.value
  const out: Cell[] = []
  for (let i = 0; i < props.rows.length; i += 1) {
    for (let j = 0; j < props.cols.length; j += 1) {
      const v = valueAt(i, j)
      const cx = g.x0 + g.cellW * (j + 0.5)
      const cy = g.y0 + g.cellH * (i + 0.5) + bowY(j, props.cols.length, g.amp)
      const key = `${i}-${j}`
      out.push({
        key,
        cx,
        cy,
        size: v > 0 ? g.cs : 1.8,
        shade: v > 0 ? shadeOfBand(v, thresholds.value) : mono.L[6],
        quiet: v <= 0,
        key3: v > 0 && v === rowMax.value[i],
        label: labelled.value.has(key) ? `${v}` : null,
        labelY: cy - g.cs / 2 - 4,
        readout: `${props.rows[i]} × ${props.cols[j]} — ${v}${props.unit}`,
        delay: i * 80 + j * 20,
      })
    }
  }
  return out
})

/** 地平线：每行一条穿过格子中心的浅弧（家具层） */
const horizons = computed(() =>
  Array.from({ length: props.rows.length }, (_, i) => {
    const g = geo.value
    const pts = props.cols.map(
      (_, j) => `${(g.x0 + g.cellW * (j + 0.5)).toFixed(2)} ${(g.y0 + g.cellH * (i + 0.5) + bowY(j, props.cols.length, g.amp)).toFixed(2)}`,
    )
    return { key: `h-${i}`, d: `M${pts.join(' L ')}`, delay: i * 80 }
  }),
)

const legend = computed(() => bandLegend(thresholds.value, max.value))
const footNote = computed(() => {
  if (!hasData.value) return ''
  const cap = cellCount.value > MAX_CELLS ? ` · 格数 ${cellCount.value} 已超 L4 的 100 格容量，建议拆图` : ''
  return `明度 ${mono.LAD.length} 档（按分位切，越黑越高） · 每行最亮格加 0.7px 描边 · 极小点 = 该组合为 0（真缺席，不是没画）${cap}`
})
</script>

<template>
  <div v-if="!hasData" class="am-empty">暂无数据（没有可交叉的组合）</div>
  <div v-else ref="host" class="am">
    <svg
      class="am-svg"
      :width="geo.w"
      :height="geo.h"
      :viewBox="`0 0 ${geo.w} ${geo.h}`"
      role="img"
      :aria-label="`弧线矩阵，${rows.length} 行 × ${cols.length} 列，最大 ${max}${unit}`"
    >
      <g class="am-g" :class="{ 'am-g--in': revealed }">
        <!-- 地平线（每行一条弧） -->
        <path
          v-for="h in horizons"
          :key="h.key"
          class="am-horizon"
          :class="{ 'am-horizon--in': revealed }"
          :d="h.d"
          fill="none"
          :stroke="mono.GRID"
          stroke-width="0.8"
          path-length="1"
          :style="{ animationDelay: `${h.delay}ms` }"
        />

        <!-- 行名 -->
        <text
          v-for="(r, i) in rows"
          :key="`r-${r}`"
          class="am-rowlab"
          :x="geo.labelW - 8"
          :y="geo.y0 + geo.cellH * (i + 0.5) + 2.6"
          text-anchor="end"
          font-size="8"
          font-weight="600"
          :fill="mono.L[2]"
          :style="{ animationDelay: `${i * 80}ms` }"
        >
          {{ r }}
        </text>

        <!-- 列名（斜上） -->
        <text
          v-for="(c, j) in cols"
          :key="`c-${c}`"
          class="am-collab"
          :x="geo.x0 + geo.cellW * (j + 0.5)"
          :y="PAD_T - 8 + bowY(j, cols.length, geo.amp)"
          :transform="`rotate(${TILT} ${geo.x0 + geo.cellW * (j + 0.5)} ${PAD_T - 8 + bowY(j, cols.length, geo.amp)})`"
          font-size="6.5"
          font-weight="700"
          letter-spacing="0.06em"
          :fill="mono.MUTED"
          :style="{ animationDelay: `${j * 20}ms` }"
        >
          {{ c }}
        </text>

        <!-- 格子 -->
        <template v-for="c in cells" :key="c.key">
          <circle
            v-if="c.quiet"
            class="am-quiet"
            :cx="c.cx"
            :cy="c.cy"
            r="0.9"
            :fill="mono.L[6]"
            :style="{ animationDelay: `${c.delay}ms` }"
          >
            <title>{{ c.readout }}</title>
          </circle>
          <rect
            v-else
            class="am-cell"
            :x="c.cx - c.size / 2"
            :y="c.cy - c.size / 2"
            :width="c.size"
            :height="c.size"
            :rx="c.size * 0.26"
            :fill="c.shade"
            :stroke="c.key3 ? mono.INK : 'none'"
            :stroke-width="c.key3 ? 0.7 : 0"
            :style="{ animationDelay: `${c.delay}ms` }"
          >
            <title>{{ c.readout }}</title>
          </rect>
          <text
            v-if="c.label"
            class="am-cellval"
            :x="c.cx"
            :y="c.labelY"
            text-anchor="middle"
            font-size="6.5"
            font-weight="800"
            :fill="mono.INK"
            :style="{ animationDelay: `${600 + c.delay}ms` }"
          >
            {{ c.label }}
          </text>
        </template>
      </g>
    </svg>

    <p class="am-foot">
      <span v-for="b in legend" :key="b.text" class="am-band">
        <i :style="{ background: b.color }" aria-hidden="true" />{{ b.text }}
      </span>
      {{ footNote }}
    </p>
  </div>
</template>

<style scoped>
.am-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88; /* mono.MUTED */
  font-size: 12.5px;
}
.am {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.am-svg {
  display: block;
  flex: 1 1 auto;
  min-height: 0;
}
.am-g {
  opacity: 0;
}
.am-g--in {
  opacity: 1;
}
.am-quiet,
.am-cell,
.am-rowlab,
.am-collab,
.am-cellval {
  transform-box: fill-box;
  transform-origin: center;
  animation: am-in 0.5s cubic-bezier(0.2, 0.7, 0.3, 1.2) both;
}
@keyframes am-in {
  from {
    opacity: 0;
    transform: scale(0.3);
  }
}
.am-horizon {
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  transition: stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}
.am-horizon--in {
  stroke-dashoffset: 0;
}
.am-foot {
  margin: 4px 0 0;
  font-size: 10px;
  color: #8f8e88; /* mono.MUTED */
  line-height: 1.7;
}
.am-band {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-right: 8px;
  color: #6a6963; /* mono.L[2] */
  font-variant-numeric: tabular-nums;
}
.am-band i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
@media (prefers-reduced-motion: reduce) {
  .am-g {
    opacity: 1;
  }
  .am-quiet,
  .am-cell,
  .am-rowlab,
  .am-collab,
  .am-cellval {
    animation: none;
  }
  .am-horizon {
    transition: none;
    stroke-dashoffset: 0;
  }
}
</style>
