<script setup lang="ts">
/**
 * **F10 Dot Heat** — lieflat Basics 组（`catalog.md`：星期×小时×量 · 小热力 · SVG）。
 * 结构正本：`templates/basics-gallery.html` · 卡内标题 `When support gets loud`
 * （渲染代码块 `// ════ C6 · dot heat ════`，副标题 `dot area = tickets · biggest cell labeled · silence stays visible`）。
 *
 * 从该卡搬过来的结构：
 * - **格子 = 点，点面积 = 数值**（用 `areaRadius` 开方换算，绝不拿数值当半径）；
 * - **静默格留一粒极小点**（模板 `TINY DOT = A QUIET HOUR`）：
 *   "这里没人来"本身是信息，空格子会把"没数据"和"安静"混为一谈；
 * - **最热格单独标注**：虚线圈 + 数值（模板 `DASHED RING = THE PEAK`）；
 * - 星期在左、小时在下（小时按可用宽度**跳着标**，不缩字号硬塞——最小 6.5px）。
 *
 * 与模板有意不同的一点（契约硬约束）：**明度用 5 档分位离散梯**（`mono.LAD`）而不是
 * 模板的 3 档定比例切分。24×7 的小格子上，连续或过细的明度差根本看不出档位；
 * 按分位切档能让每一档都有格子落进去（数据偏斜时定比例切分会把 90% 格子压进一档）。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { bandLegend, quantileBands, shadeOfBand } from './bands'
import { areaRadius, mono } from './mono'

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

/** 明度档数（离散，越黑越高） */
const BANDS = mono.LAD.length
const PAD_T = 6
const PAD_B = 20
const PAD_R = 6

const host = ref<HTMLElement | null>(null)
const box = ref({ w: 400, h: 230 })
let ro: ResizeObserver | null = null

onMounted(() => {
  const node = host.value
  if (!node) return
  const read = (): void => {
    box.value = { w: Math.max(180, node.clientWidth), h: Math.max(100, node.clientHeight) }
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

const shapeOk = computed(
  () => props.rows.length > 0 && props.cols.length > 0 && props.matrix.length >= props.rows.length,
)
const max = computed(() => {
  let m = 0
  for (let i = 0; i < props.rows.length; i += 1) {
    for (let j = 0; j < props.cols.length; j += 1) m = Math.max(m, valueAt(i, j))
  }
  return m
})
const hasData = computed(() => shapeOk.value && max.value > 0)

/** 分位阈值：把"有数的格子"按分位切 5 档 —— 每档都装得下格子 */
const thresholds = computed(() => {
  const pool: number[] = []
  for (let i = 0; i < props.rows.length; i += 1) {
    for (let j = 0; j < props.cols.length; j += 1) {
      const v = valueAt(i, j)
      if (v > 0) pool.push(v)
    }
  }
  return quantileBands(pool, BANDS)
})

/** 值 → 档位 → 灰阶（越黑越高） */
const shadeOf = (v: number): string => shadeOfBand(v, thresholds.value)

const geo = computed(() => {
  const { w, h } = box.value
  const labelW = Math.min(w * 0.3, Math.max(...props.rows.map((r) => r.length), 1) * 7 + 12)
  const innerW = Math.max(40, w - labelW - PAD_R)
  const innerH = Math.max(30, h - PAD_T - PAD_B)
  const cellW = innerW / Math.max(props.cols.length, 1)
  const cellH = innerH / Math.max(props.rows.length, 1)
  return {
    w,
    h,
    labelW,
    cellW,
    cellH,
    x0: labelW,
    y0: PAD_T,
    rMax: Math.max(2, Math.min(cellW, cellH) * 0.44),
    /** 小时标签步长：至少留 18px，装不下就跳着标，不缩字号 */
    stride: Math.max(1, Math.ceil(props.cols.length / Math.max(1, Math.floor(innerW / 20)))),
  }
})

interface Cell {
  key: string
  cx: number
  cy: number
  r: number
  fill: string
  hero: boolean
  delay: number
  readout: string
}

const cells = computed<Cell[]>(() => {
  if (!hasData.value) return []
  const g = geo.value
  const out: Cell[] = []
  for (let i = 0; i < props.rows.length; i += 1) {
    for (let j = 0; j < props.cols.length; j += 1) {
      const v = valueAt(i, j)
      out.push({
        key: `${i}-${j}`,
        cx: g.x0 + g.cellW * (j + 0.5),
        cy: g.y0 + g.cellH * (i + 0.5),
        r: v > 0 ? Math.max(1.4, areaRadius(v, max.value, g.rMax)) : 0.9,
        fill: v > 0 ? shadeOf(v) : mono.L[6],
        hero: v > 0 && v === max.value,
        // 与模板同节奏：每行 50ms、每格 15ms（斜向铺开）
        delay: i * 50 + j * 15,
        readout: `${props.rows[i]} ${props.cols[j]} — ${v}${props.unit}`,
      })
    }
  }
  return out
})

const heroCell = computed(() => cells.value.find((c) => c.hero))
const colTicks = computed(() =>
  props.cols.map((label, j) => ({ label, j })).filter(({ j }) => j % geo.value.stride === 0),
)
const legend = computed(() => bandLegend(thresholds.value, max.value))
</script>

<template>
  <div v-if="!hasData" class="dh-empty">暂无数据（该区间没有任何采样格）</div>
  <div v-else ref="host" class="dh">
    <svg
      class="dh-svg"
      :width="geo.w"
      :height="geo.h"
      :viewBox="`0 0 ${geo.w} ${geo.h}`"
      role="img"
      :aria-label="`点阵热力图，${rows.length} 行 × ${cols.length} 列，峰值 ${max}${unit}`"
    >
      <g class="dh-g" :class="{ 'dh-g--in': revealed }">
        <!-- 行标签（星期） -->
        <text
          v-for="(r, i) in rows"
          :key="`r-${r}`"
          class="dh-rowlab"
          :x="geo.labelW - 8"
          :y="geo.y0 + geo.cellH * (i + 0.5) + 2.6"
          text-anchor="end"
          font-size="7.5"
          font-weight="700"
          letter-spacing="0.04em"
          :fill="mono.L[2]"
          :style="{ animationDelay: `${i * 40}ms` }"
        >
          {{ r }}
        </text>

        <!-- 点：面积 = 数值（sqrt），明度 = 分位档 -->
        <circle
          v-for="c in cells"
          :key="c.key"
          class="dh-dot"
          :cx="c.cx"
          :cy="c.cy"
          :r="c.r"
          :fill="c.fill"
          :style="{ animationDelay: `${c.delay}ms` }"
        >
          <title>{{ c.readout }}</title>
        </circle>

        <!-- 最热格：虚线圈（第二编码，不靠颜色抢视线） -->
        <circle
          v-if="heroCell"
          class="dh-hero"
          :cx="heroCell.cx"
          :cy="heroCell.cy"
          :r="heroCell.r + 3.4"
          fill="none"
          :stroke="mono.INK"
          stroke-width="1"
          stroke-dasharray="2 3"
          :style="{ animationDelay: '900ms' }"
        />
        <text
          v-if="heroCell"
          class="dh-heroval"
          :x="heroCell.cx"
          :y="heroCell.cy - heroCell.r - 6"
          text-anchor="middle"
          font-size="9"
          font-weight="800"
          :fill="mono.INK"
          :style="{ animationDelay: '960ms' }"
        >
          {{ max }}<tspan v-if="unit" font-size="6.5" :fill="mono.MUTED">{{ unit }}</tspan>
        </text>

        <!-- 列标签（小时）：按可用宽度跳着标 -->
        <text
          v-for="t in colTicks"
          :key="`c-${t.label}`"
          class="dh-collab"
          :x="geo.x0 + geo.cellW * (t.j + 0.5)"
          :y="geo.y0 + geo.cellH * rows.length + 13"
          text-anchor="middle"
          font-size="6.5"
          font-weight="600"
          :fill="mono.L[3]"
          :style="{ animationDelay: `${t.j * 20}ms` }"
        >
          {{ t.label }}
        </text>
      </g>
    </svg>

    <p class="dh-foot">
      <span class="dh-key">明度 {{ BANDS }} 档（按分位切）</span>
      <span v-for="b in legend" :key="b.text" class="dh-band">
        <i :style="{ background: b.color }" aria-hidden="true" />{{ b.text }}
      </span>
      点面积 = 数值 · 极小点 = 静默 · 虚线圈 = 峰值 {{ max }}{{ unit }} · 每格 hover 出全量
    </p>
  </div>
</template>

<style scoped>
.dh-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88; /* mono.MUTED */
  font-size: 12.5px;
}
.dh {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.dh-svg {
  display: block;
  flex: 1 1 auto;
  min-height: 0;
}
.dh-g {
  opacity: 0;
}
.dh-g--in {
  opacity: 1;
}
.dh-dot,
.dh-rowlab,
.dh-collab,
.dh-hero,
.dh-heroval {
  transform-box: fill-box;
  transform-origin: center;
  animation: dh-in 0.5s cubic-bezier(0.2, 0.7, 0.3, 1.2) both;
}
@keyframes dh-in {
  from {
    opacity: 0;
    transform: scale(0.2);
  }
}
.dh-foot {
  margin: 4px 0 0;
  font-size: 10px;
  color: #8f8e88; /* mono.MUTED */
  line-height: 1.6;
}
.dh-key {
  margin-right: 6px;
}
.dh-band {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-right: 8px;
  color: #6a6963; /* mono.L[2] */
  font-variant-numeric: tabular-nums;
}
.dh-band i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
@media (prefers-reduced-motion: reduce) {
  .dh-g {
    opacity: 1;
  }
  .dh-dot,
  .dh-rowlab,
  .dh-collab,
  .dh-hero,
  .dh-heroval {
    animation: none;
  }
}
</style>
