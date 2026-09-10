<script setup lang="ts">
/**
 * **F3 Hairline Area** — lieflat Basics 组（`catalog.md`：日序列 30–60 天 · 看形态 · SVG）。
 * 结构正本：`templates/basics-gallery.html` · 卡内标题 `Concurrent users, filled with days`
 * （渲染代码块 `// ════ B3 · hairline area ════`，副标题 `the area is made of days, not paint`）。
 *
 * 从该卡搬过来的结构：
 * - **面积不是色块，是"一天一根发丝"**：每天从地板立一根竖发丝到当天峰值，面积由日子组成。
 *   这条是 F3 与"渐变填充面积图"的分界线，也是它和 F2 的姊妹关系（F2 = 同一根发丝不填充）；
 * - 顶边一根 1.2px 收轮廓线（模板 `stroke-width:1.2`）+ 描线入场（`pathLength` 归一到 1）；
 * - **峰值日加重**：模板给峰值日一根更黑更粗的发丝（不用圆点——圆点在非等比拉伸下会变椭圆，
 *   与 `HairlineLine` 的刻度同理），峰值读数放**外层 HTML**；
 * - 逐日读数靠透明命中条 + 原生 `<title>`：零 JS、逐日可查。
 *
 * `stacked` 是本仓库扩展（契约要求）：堆叠时同一根竖发丝画在"下沿→上沿"之间，
 * 面积仍由日子组成；段序按 `mono.L` 明度阶梯分配（明度即序列重要性），不加任何色相。
 */
import { computed } from 'vue'

import type { LineSeries } from './HairlineLine.vue'

import { mono, scale } from './mono'

const props = withDefaults(
  defineProps<{
    labels: string[]
    series: LineSeries[]
    unit?: string
    /** 堆叠构成：每根发丝画在"下沿→上沿"之间，同时看总量 */
    stacked?: boolean
    revealed?: boolean
  }>(),
  { unit: '', stacked: false, revealed: true },
)

/** 固定坐标系：横向拉伸（`preserveAspectRatio="none"`）+ `non-scaling-stroke` 保住发丝 */
const VW = 100
const VH = 100
/** 地板抬高一点，避免"0"被裁 */
const FLOOR = 4
/** 顶部留白：峰值不贴边 */
const PAD_T = 6

const n = computed(() => props.labels.length)

/** null = 当天没有采样：不画发丝（不是 0，0 是"有采样且为零"） */
const valueAt = (s: LineSeries, i: number): number | null => {
  const v = s.values[i]
  return v === null || v === undefined || !Number.isFinite(v) ? null : v
}

const totals = computed(() =>
  Array.from({ length: n.value }, (_, i) =>
    props.series.reduce((sum, s) => sum + (valueAt(s, i) ?? 0), 0),
  ),
)

const domainMax = computed(() => {
  const pool = props.stacked
    ? totals.value
    : props.series.flatMap((s) => s.values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v)))
  const raw = pool.length ? Math.max(...pool) : 0
  return raw > 0 ? raw : 0
})

const hasData = computed(
  () =>
    n.value > 0 &&
    props.series.some((s) => s.values.some((v) => typeof v === 'number' && Number.isFinite(v))) &&
    domainMax.value > 0,
)

const xAt = (i: number): number => (n.value <= 1 ? VW / 2 : (i / (n.value - 1)) * VW)
const yAt = (v: number): number => VH - FLOOR - scale(v, 0, domainMax.value, 0, VH - FLOOR - PAD_T)

interface Hair {
  key: string
  x: number
  y1: number
  y2: number
  color: string
  width: number
  opacity: number
  delay: number
}

interface Layer {
  name: string
  color: string
  path: string
}

interface Band {
  lower: number[]
  upper: number[]
}

/** 累积上下沿（堆叠用）：与序列顺序一致，第 0 段贴地板 */
const bands = computed<Band[]>(() => {
  let acc = Array.from({ length: n.value }, () => 0)
  return props.series.map((s) => {
    const lower = [...acc]
    acc = acc.map((v, i) => v + (valueAt(s, i) ?? 0))
    return { lower, upper: [...acc] }
  })
})

/** 峰值日：堆叠看合计最大的一天，非堆叠看"最大的那个单点"落在哪天 */
const peakIndex = computed(() => {
  const target = domainMax.value
  if (props.stacked) return totals.value.findIndex((t) => t === target)
  for (let i = 0; i < n.value; i += 1) {
    if (props.series.some((s) => valueAt(s, i) === target)) return i
  }
  return -1
})

const hairs = computed<Hair[]>(() => {
  const out: Hair[] = []
  props.series.forEach((s, si) => {
    const color = mono.L[Math.min(s.tone ?? si, mono.L.length - 1)]
    const band = bands.value[si]
    for (let i = 0; i < n.value; i += 1) {
      const raw = valueAt(s, i)
      if (raw === null) continue
      const top = props.stacked ? band.upper[i] : raw
      const bottom = props.stacked ? band.lower[i] : 0
      const isPeak = !props.stacked && i === peakIndex.value
      out.push({
        key: `${s.name}-${i}`,
        x: xAt(i),
        y1: yAt(bottom),
        y2: yAt(top),
        color: isPeak ? mono.L[0] : color,
        width: isPeak ? 1.2 : 0.55,
        opacity: isPeak ? 1 : props.stacked ? 0.62 + (si % 2) * 0.2 : 0.34 + (si % 3) * 0.12,
        delay: i * mono.MOTION.staggerDot,
      })
    }
  })
  return out
})

/** 顶边收轮廓：堆叠 = 总量，非堆叠 = 各序列自己的顶边 */
const layers = computed<Layer[]>(() => {
  if (props.stacked) {
    const pts = totals.value.map((v, i) => `${xAt(i).toFixed(2)} ${yAt(v).toFixed(2)}`).join(' L ')
    return [{ name: '合计', color: mono.L[0], path: `M${pts}` }]
  }
  return props.series.map((s, si) => {
    const segs: string[] = []
    let pen = false
    for (let i = 0; i < n.value; i += 1) {
      const v = valueAt(s, i)
      if (v === null) {
        pen = false
        continue
      }
      segs.push(`${pen ? 'L' : 'M'}${xAt(i).toFixed(2)} ${yAt(v).toFixed(2)}`)
      pen = true
    }
    return { name: s.name, color: mono.L[Math.min(s.tone ?? si, mono.L.length - 1)], path: segs.join(' ') }
  })
})

const peakValue = computed(() => (props.stacked ? totals.value[peakIndex.value] ?? 0 : domainMax.value))
const peakLabel = computed(() => props.labels[peakIndex.value] ?? '')
const peakSeries = computed(() => {
  if (props.stacked) return '合计'
  return props.series.find((s) => (s.values[peakIndex.value] ?? 0) === domainMax.value)?.name ?? ''
})
const fmt = (v: number): string => String(Math.round(v * 100) / 100)
/** 逐日读数：单序列只报一个数，多序列逐条报 */
const dayReadout = (i: number): string => {
  const head = props.labels[i] ?? String(i + 1)
  if (props.stacked) return `${head}　合计 ${fmt(totals.value[i] ?? 0)}${props.unit}`
  const parts = props.series.map((s) => {
    const v = valueAt(s, i)
    return `${s.name} ${v === null ? '—' : fmt(v)}${props.unit}`
  })
  return `${head}　${parts.join('　')}`
}
/** 命中条：整列一个热区，原生 <title> 出逐日读数（零 JS） */
const hits = computed(() => {
  const w = VW / Math.max(n.value, 1)
  return props.labels.map((label, i) => ({
    key: `${label}-${i}`,
    x: Math.max(0, xAt(i) - w / 2),
    w,
    readout: dayReadout(i),
  }))
})
</script>

<template>
  <div v-if="!hasData" class="ha-empty">暂无数据（该区间没有采样点）</div>
  <div v-else class="ha">
    <svg
      class="ha-svg"
      :viewBox="`0 0 ${VW} ${VH}`"
      preserveAspectRatio="none"
      role="img"
      :aria-label="`面积图，${series.map((s) => s.name).join('、')}，共 ${n} 天，峰值 ${fmt(peakValue)}${unit}`"
    >
      <line
        :x1="0"
        :x2="VW"
        :y1="VH - FLOOR"
        :y2="VH - FLOOR"
        :stroke="mono.GRID"
        stroke-width="0.7"
        vector-effect="non-scaling-stroke"
      />

      <g class="ha-g" :class="{ 'ha-g--in': revealed }">
        <!-- 面积 = 一天一根发丝（地板立到当天峰值） -->
        <line
          v-for="h in hairs"
          :key="h.key"
          class="ha-hair"
          :x1="h.x"
          :x2="h.x"
          :y1="h.y1"
          :y2="h.y2"
          :stroke="h.color"
          :stroke-width="h.width"
          :opacity="h.opacity"
          vector-effect="non-scaling-stroke"
          :style="{ animationDelay: `${h.delay}ms` }"
        />
        <!-- 顶边收轮廓 -->
        <path
          v-for="l in layers"
          :key="`edge-${l.name}`"
          class="ha-edge"
          :class="{ 'ha-edge--in': revealed }"
          :d="l.path"
          fill="none"
          :stroke="l.color"
          stroke-width="1.2"
          stroke-linejoin="round"
          stroke-linecap="round"
          vector-effect="non-scaling-stroke"
          path-length="1"
        />
      </g>

      <!-- 命中条：整列数据都在这，零 JS 出读数 -->
      <rect
        v-for="h in hits"
        :key="`hit-${h.key}`"
        :x="h.x"
        y="0"
        :width="h.w"
        :height="VH"
        fill="transparent"
      >
        <title>{{ h.readout }}</title>
      </rect>
    </svg>

    <!-- 端点/峰值放外层 HTML：文字不进入被横向拉伸的 SVG -->
    <div class="ha-axis">
      <span>{{ labels[0] }}</span>
      <span class="ha-peak">
        峰值 {{ fmt(peakValue) }}{{ unit }}<template v-if="stacked"> · 合计</template>
        <template v-else-if="peakSeries"> · {{ peakSeries }}</template>
        <template v-if="peakLabel">（{{ peakLabel }}）</template>
      </span>
      <span>{{ labels[labels.length - 1] }}</span>
    </div>

    <ul v-if="series.length > 1" class="ha-legend">
      <li v-for="(s, si) in series" :key="`lg-${s.name}`">
        <i :style="{ background: mono.L[Math.min(s.tone ?? si, mono.L.length - 1)] }" aria-hidden="true" />{{ s.name }}
      </li>
      <li v-if="stacked" class="ha-legend-note">堆叠：段序 = 明度序（越黑越靠下）</li>
    </ul>
  </div>
</template>

<style scoped>
.ha-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88; /* mono.MUTED */
  font-size: 12.5px;
}
.ha {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.ha-svg {
  display: block;
  width: 100%;
  flex: 1 1 auto;
  min-height: 0;
  overflow: visible;
}
.ha-g {
  opacity: 0;
}
.ha-g--in {
  opacity: 1;
}
.ha-hair {
  animation: ha-rise 0.7s cubic-bezier(0.25, 1, 0.5, 1) both;
  transform-origin: bottom;
}
@keyframes ha-rise {
  from {
    opacity: 0;
  }
}
.ha-edge {
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  transition: stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1) 0.35s;
}
.ha-edge--in {
  stroke-dashoffset: 0;
}
.ha-axis {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-top: 6px;
  font-size: 10px;
  color: #8f8e88; /* mono.MUTED */
  font-variant-numeric: tabular-nums;
}
.ha-peak {
  color: #4a4944; /* mono.L[1] */
  font-weight: 700;
}
.ha-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
  font-size: 10.5px;
  color: #6a6963; /* mono.L[2] */
}
.ha-legend li {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.ha-legend i {
  width: 9px;
  height: 2px;
  border-radius: 1px;
}
.ha-legend-note {
  color: #8f8e88; /* mono.MUTED */
}
@media (prefers-reduced-motion: reduce) {
  .ha-g {
    opacity: 1;
  }
  .ha-hair {
    animation: none;
  }
  .ha-edge {
    transition: none;
    stroke-dashoffset: 0;
  }
}
</style>
