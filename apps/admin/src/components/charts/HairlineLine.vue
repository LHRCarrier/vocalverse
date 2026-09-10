<script setup lang="ts">
/**
 * **F2 Hairline Line** — lieflat Basics 组。
 * 结构正本：`templates/basics-gallery.html` · 卡内标题 `Thirty days of sign-ups`
 * （数据形状：日序列 ≤30 天，逐日读数；引擎：手写 SVG）。
 *
 * 编码契约（SKILL §2）：
 * - **发丝线**：stroke 0.5–0.7px，用 `vector-effect="non-scaling-stroke"` 保住，
 *   不随容器拉伸变粗；
 * - **明度即数据**：多序列按重要性从 `L[0]`（最黑）往浅分配，不按顺序随便拿；
 * - **逐日读数**：每天一个刻痕（tick），不做圆点——圆点在非等比缩放下会变成椭圆，
 *   而竖刻痕 + non-scaling-stroke 在任何宽度下都是干净的竖线（lieflat 的 tick 语汇）；
 * - **悬停见数**：透明命中矩形 + 原生 `<title>`，零 JS 拿到逐日读数；
 * - **文字不进被拉伸的 SVG**：横轴端点与峰值放外层 HTML（否则字会被横向拉变形）；
 * - 无数据 → 明确"暂无数据"，不画一条贴底的假线（那是"没数据"与"全是 0"分不清）。
 */
import { computed } from 'vue'

import { mono, scale } from './mono'

export interface LineSeries {
  name: string
  values: (number | null)[]
  /** 灰阶层级：0 = 最重要（最黑）。默认按序列顺序 0,1,2… */
  tone?: number
}

const props = withDefaults(
  defineProps<{
    labels: string[]
    series: LineSeries[]
    unit?: string
    /** 数值格式化（tooltip / 端点读数） */
    format?: (v: number) => string
    /** 起点是否锚定 0（错误率等"占比"类必须锚 0，否则会夸大波动） */
    zeroBased?: boolean
    revealed?: boolean
  }>(),
  {
    unit: '',
    zeroBased: false,
    revealed: true,
    format: (v: number) => String(Math.round(v * 100) / 100),
  },
)

/** 坐标系固定 0–100 × 0–100，宽度随容器伸缩 → 所以下面全是百分比坐标 */
const VW = 100
const VH = 100
/** 顶/底留白，避免峰值贴边被裁 */
const PAD = 6

const allValues = computed(() =>
  props.series.flatMap((s) => s.values.filter((v): v is number => v !== null && Number.isFinite(v))),
)

const domain = computed(() => {
  const vals = allValues.value
  if (!vals.length) return { min: 0, max: 1 }
  const rawMax = Math.max(...vals)
  const rawMin = props.zeroBased ? 0 : Math.min(...vals)
  // 全等值时给一个人造区间，避免除零；同时不假装有波动
  if (rawMax === rawMin) {
    return rawMin === 0 ? { min: 0, max: 1 } : { min: rawMin * 0.98, max: rawMax * 1.02 }
  }
  return { min: props.zeroBased ? 0 : rawMin, max: rawMax }
})

const n = computed(() => props.labels.length)

function xAt(i: number): number {
  return n.value <= 1 ? VW / 2 : (i / (n.value - 1)) * VW
}

function yAt(v: number): number {
  const { min, max } = domain.value
  return VH - PAD - scale(v, min, max, 0, VH - PAD * 2)
}

interface RenderedSeries {
  name: string
  color: string
  path: string
  ticks: { x: number; y: number; value: number; label: string }[]
}

const rendered = computed<RenderedSeries[]>(() =>
  props.series.map((s, si) => {
    const color = mono.L[Math.min(s.tone ?? si, mono.L.length - 1)]
    const pts: { x: number; y: number; value: number; label: string }[] = []
    const segs: string[] = []
    let pen = false

    s.values.forEach((v, i) => {
      if (v === null || !Number.isFinite(v)) {
        pen = false
        return
      }
      const x = xAt(i)
      const y = yAt(v)
      segs.push(`${pen ? 'L' : 'M'}${x.toFixed(2)} ${y.toFixed(2)}`)
      pen = true
      pts.push({ x, y, value: v, label: props.labels[i] ?? String(i) })
    })

    return { name: s.name, color, path: segs.join(' '), ticks: pts }
  }),
)

const peak = computed(() => (allValues.value.length ? Math.max(...allValues.value) : 0))
const hitWidth = computed(() => VW / Math.max(n.value - 1, 1))
const hasData = computed(() => allValues.value.length > 0)
</script>

<template>
  <div v-if="!hasData" class="hl-empty">暂无数据（该区间没有采样点）</div>
  <div v-else class="hl">
    <svg
      class="hl-svg"
      :viewBox="`0 0 ${VW} ${VH}`"
      preserveAspectRatio="none"
      role="img"
      :aria-label="`折线图，${series.map((s) => s.name).join('、')}，共 ${n} 个数据点，峰值 ${format(peak)}${unit}`"
    >
      <!-- 底线：给了"0 在哪"的参照，避免读者以为线是从底部长出来的 -->
      <line
        :x1="0"
        :x2="VW"
        :y1="VH - PAD"
        :y2="VH - PAD"
        :stroke="mono.GRID"
        stroke-width="0.6"
        vector-effect="non-scaling-stroke"
      />

      <g v-for="s in rendered" :key="s.name">
        <!-- 逐日刻痕：非等比缩放下仍是干净竖线 -->
        <line
          v-for="(tk, i) in s.ticks"
          :key="`${s.name}-t-${i}`"
          :x1="tk.x"
          :x2="tk.x"
          :y1="tk.y"
          :y2="VH - PAD"
          :stroke="s.color"
          stroke-width="0.55"
          :opacity="revealed ? 0.34 : 0"
          vector-effect="non-scaling-stroke"
          class="hl-tick"
          :style="{ animationDelay: `${i * 12}ms` }"
        />
        <!-- 发丝主线 -->
        <path
          :d="s.path"
          fill="none"
          :stroke="s.color"
          stroke-width="0.7"
          stroke-linejoin="round"
          stroke-linecap="round"
          vector-effect="non-scaling-stroke"
          class="hl-line"
          :class="{ 'hl-line--in': revealed }"
        />
      </g>

      <!-- 悬停命中区：透明矩形 + 原生 title（零 JS 读数） -->
      <rect
        v-for="(label, i) in labels"
        :key="`hit-${i}`"
        :x="Math.max(0, xAt(i) - hitWidth / 2)"
        y="0"
        :width="hitWidth"
        :height="VH"
        fill="transparent"
      >
        <title>{{ label }}　{{ series.map((s) => `${s.name} ${s.values[i] === null || s.values[i] === undefined ? '—' : format(s.values[i] as number)}${unit}`).join('　') }}</title>
      </rect>
    </svg>

    <!-- 端点与峰值放外层 HTML：文字不进入被横向拉伸的 SVG -->
    <div class="hl-axis">
      <span>{{ labels[0] }}</span>
      <span class="hl-peak">峰值 {{ format(peak) }}{{ unit }}</span>
      <span>{{ labels[labels.length - 1] }}</span>
    </div>

    <ul v-if="series.length > 1" class="hl-legend">
      <li v-for="s in rendered" :key="`lg-${s.name}`">
        <i :style="{ background: s.color }" aria-hidden="true" />{{ s.name }}
      </li>
    </ul>
  </div>
</template>

<style scoped>
.hl-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88;
  font-size: 12.5px;
}
.hl {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.hl-svg {
  display: block;
  width: 100%;
  flex: 1 1 auto;
  min-height: 0;
  overflow: visible;
}
.hl-tick {
  animation: hl-tick 0.5s cubic-bezier(0.25, 1, 0.5, 1) both;
}
@keyframes hl-tick {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
}
.hl-line {
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  transition: stroke-dashoffset 0.9s cubic-bezier(0.4, 0, 0.2, 1);
  /* pathLength 归一化：任意长度都走一遍同样节奏的描线 */
  path-length: 1;
}
.hl-line--in {
  stroke-dashoffset: 0;
}
.hl-axis {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-top: 6px;
  font-size: 10px;
  color: #8f8e88;
  font-variant-numeric: tabular-nums;
}
.hl-peak {
  color: #6a6963;
  font-weight: 600;
}
.hl-legend {
  display: flex;
  gap: 14px;
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
  font-size: 10.5px;
  color: #6a6963;
}
.hl-legend li {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.hl-legend i {
  width: 9px;
  height: 2px;
  border-radius: 1px;
}
@media (prefers-reduced-motion: reduce) {
  .hl-tick,
  .hl-line {
    animation: none;
    transition: none;
    stroke-dashoffset: 0;
    opacity: 1;
  }
}
</style>
