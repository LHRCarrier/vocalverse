<script lang="ts">
import type { EChartsType } from 'echarts/core'

/**
 * 模块级状态：ECharts 按需注册只做一次（同页多实例不必重复 `use()`）。
 * 这一块写在 `<script setup>` 之外的普通 `<script>` 里 —— 它只在模块加载时执行一次，
 * 而 `<script setup>` 每个实例都会跑一遍。
 */
let registered = false

async function loadECharts(): Promise<typeof import('echarts/core')> {
  const core = await import('echarts/core')
  if (!registered) {
    const { LineChart } = await import('echarts/charts')
    const { GridComponent, TooltipComponent } = await import('echarts/components')
    const { CanvasRenderer } = await import('echarts/renderers')
    core.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])
    registered = true
  }
  return core
}

/** Mono 实心色 + 透明度（Glance 里唯一允许的透明用法：面积渐隐编码"量在流动"） */
function withAlpha(hex: string, alpha: number): string {
  const r = Number.parseInt(hex.slice(1, 3), 16)
  const g = Number.parseInt(hex.slice(3, 5), 16)
  const b = Number.parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

type Chart = EChartsType
</script>

<script setup lang="ts">
/**
 * **G17 Dynamic Stream** — lieflat Glance 系（`catalog.md`：实时滚动序列 · 直播/大屏 · ECharts）。
 * 结构正本：`templates/glance-gallery.html` · 卡内标题 `Concurrent users, streaming`
 * （渲染代码块 `// ════ mono-fancy4 · 2: dynamic data stream ════`，
 * 副标题 `one new reading every 300ms · window of 50 · click to restart`）。
 *
 * 为什么这张用 Glance + ECharts：Glance 是"提前聚合、三秒读完"的降级档，
 * 只有 dashboard/监控场景才允许（契约已注明）。滚动序列的绘制/增量更新交给引擎，
 * **但样式必须套 `echartsMonoBase`，且 series 颜色一律从 `mono.L` 取**——
 * 不碰 ECharts 默认配色（那是"退回图表库默认样式"，SKILL 第零节明令禁止）。
 *
 * 从该卡搬过来的结构：
 * - **窗口制**：只画最近 `windowSize` 个读数（模板 `WIN=50`），x 轴是相对序号，刻度全隐；
 * - **粗笔画**（模板 `lineStyle.width:2.4`）+ `smooth:.45` + `symbol:'none'`：Glance 的笔画必须理直气壮；
 * - **端点读数**（模板 `endLabel` fontSize 14 / weight 800）—— 曲线右端直接报当前值，
 *   这就是 `grid.right:58` 的来源；
 * - **面积渐隐**（模板 `rgba(28,28,26,.16) → 0`）：只有单序列时才铺，
 *   多序列铺面积会把"两条各占多少"糊成一片；
 * - **LIVE 徽标**（模板 `graphic`）改成外层 HTML 的一个小圆点 + 字，字号不被画布缩放牵连。
 *
 * 与模板的两点差异（都是"组件不该有定时器"这条约束的后果）：
 * 1. **本组件不自带 `setInterval`**（契约：只渲染传入数据，数据由页面轮询后传入），
 *    所以"每 300ms 推一个点"的节奏由调用方决定，组件只负责把新窗口画出来；
 * 2. y 轴按数据上下留 15% 余量（模板写死 `min:20,max:130`）——线图的这一档放大
 *    是 Glance 的读法，但为了让读者知道自己看的是哪一段，**真实区间写在脚注里**，
 *    不靠猜（柱状图的"绝不截断"契约管的是长度编码，这里位置才是数据）。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { EChartsOption } from 'echarts'

import { echartsMonoBase, mono, prefersReducedMotion } from './mono'

export interface StreamSeries {
  name: string
  values: number[]
}

const props = withDefaults(
  defineProps<{
    series: StreamSeries[]
    unit?: string
    /** 滚动窗口长度（点数） */
    windowSize?: number
    revealed?: boolean
  }>(),
  { unit: '', windowSize: 60, revealed: true },
)

const plot = ref<HTMLElement | null>(null)
let chart: Chart | null = null
let ro: ResizeObserver | null = null

/** 截窗口：每序列只保留最近 N 个读数；长度不一的时候后端补 null，不猜值 */
const windowed = computed(() => {
  const win = Math.max(2, Math.round(props.windowSize))
  const clean = props.series.filter((s) => Array.isArray(s.values))
  const len = Math.max(...clean.map((s) => s.values.slice(-win).length), 0)
  return clean.map((s) => {
    const tail = s.values.slice(-win)
    return { name: s.name, values: [...Array(Math.max(0, len - tail.length)).fill(null), ...tail] }
  })
})

const hasData = computed(
  () =>
    windowed.value.length > 0 &&
    windowed.value.some((s) => s.values.some((v) => typeof v === 'number' && Number.isFinite(v))),
)

const stats = computed(() => {
  const all = windowed.value.flatMap((s) => s.values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v)))
  if (!all.length) return { lo: 0, hi: 0, last: [] as { name: string; value: number | null; color: string }[] }
  return {
    lo: Math.min(...all),
    hi: Math.max(...all),
    last: windowed.value.map((s, si) => {
      const tail = [...s.values].reverse().find((v) => typeof v === 'number' && Number.isFinite(v))
      return {
        name: s.name,
        value: typeof tail === 'number' ? tail : null,
        color: mono.L[Math.min(si, mono.L.length - 1)],
      }
    }),
  }
})

function buildOption(animate: boolean): EChartsOption {
  const rows = windowed.value
  const len = rows[0]?.values.length ?? 0
  const { lo, hi } = stats.value
  const pad = hi > lo ? (hi - lo) * 0.15 : Math.max(1, Math.abs(hi) * 0.1)
  return {
    backgroundColor: echartsMonoBase.backgroundColor,
    animation: animate,
    // 入场用 Mono 的 900ms quarticOut；滚动更新用模板的 260ms linear（一个读数一段平移）
    animationDuration: echartsMonoBase.animationDuration,
    animationEasing: echartsMonoBase.animationEasing,
    animationDurationUpdate: 260,
    animationEasingUpdate: 'linear',
    textStyle: echartsMonoBase.textStyle,
    tooltip: {
      ...echartsMonoBase.tooltip,
      // `mono.tipLight` 是 `as const`，padding 会推成 readonly 元组；ECharts 要可写数组，这里显式铺一次
      padding: [10, 14],
      trigger: 'axis' as const,
      valueFormatter: (v: unknown): string => `${v}${props.unit}`,
    },
    grid: { left: 14, right: 58, top: 34, bottom: 14, containLabel: false },
    xAxis: {
      type: 'category',
      data: rows[0]?.values.map((_, i) => String(i - len + 1)) ?? [],
      boundaryGap: false,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false },
    },
    yAxis: { type: 'value', show: false, min: lo - pad, max: hi + pad },
    series: rows.map((s, si) => {
      const color = mono.L[Math.min(si, mono.L.length - 1)]
      return {
        type: 'line' as const,
        name: s.name,
        data: s.values as (number | null)[],
        smooth: 0.45,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { color, width: 2.4 },
        itemStyle: { color },
        // 面积只在单序列时铺：多序列铺面积会把构成糊掉（Glance 也只需要看总量走势）
        areaStyle:
          rows.length === 1
            ? {
                color: {
                  type: 'linear' as const,
                  x: 0,
                  y: 0,
                  x2: 0,
                  y2: 1,
                  colorStops: [
                    { offset: 0, color: withAlpha(color, 0.16) },
                    { offset: 1, color: withAlpha(color, 0) },
                  ],
                },
              }
            : undefined,
        endLabel: {
          show: true,
          color,
          fontSize: 14,
          fontWeight: 800,
          formatter: (p: { value?: unknown }): string =>
            typeof p.value === 'number' ? `${p.value}${props.unit}` : '',
        },
      }
    }),
  }
}

/** 只有 `revealed` 且用户没要求减弱动效时才播入场 */
function animate(): boolean {
  return props.revealed && !prefersReducedMotion()
}

async function ensureChart(): Promise<void> {
  const node = plot.value
  if (!node || chart) return
  const core = await loadECharts()
  if (!plot.value) return
  chart = core.init(node, undefined, { renderer: 'canvas' })
  chart.setOption(buildOption(animate()))
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => chart?.resize())
    ro.observe(node)
  }
}

onMounted(() => {
  void ensureChart()
})

onBeforeUnmount(() => {
  ro?.disconnect()
  ro = null
  chart?.dispose()
  chart = null
})

watch([() => props.series, () => props.revealed, () => props.windowSize], () => {
  if (!hasData.value) return
  void ensureChart().then(() => chart?.setOption(buildOption(animate())))
}, { deep: true })

const footNote = computed(() => {
  if (!hasData.value) return ''
  const w = Math.max(2, Math.round(props.windowSize))
  return `窗口 = 最近 ${Math.min(w, windowed.value[0]?.values.length ?? 0)} 个读数 · 纵轴区间 ${stats.value.lo}–${stats.value.hi}${props.unit}（已留 15% 余量） · 数据由页面轮询传入，组件不自己开定时器`
})
</script>

<template>
  <div v-if="!hasData" class="ds-empty">暂无数据（还没有推上来的读数）</div>
  <div v-else class="ds">
    <div class="ds-head">
      <span class="ds-live" aria-hidden="true" />
      <span class="ds-live-text">实时</span>
      <ul class="ds-legend">
        <li v-for="l in stats.last" :key="l.name">
          <i :style="{ background: l.color }" aria-hidden="true" />{{ l.name }}
          <b>{{ l.value === null ? '—' : l.value }}{{ unit }}</b>
        </li>
      </ul>
    </div>
    <div ref="plot" class="ds-plot" role="img" :aria-label="`实时滚动折线图，窗口 ${windowSize} 点，共 ${series.length} 条序列`" />
    <p class="ds-foot">{{ footNote }}</p>
  </div>
</template>

<style scoped>
.ds-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88; /* mono.MUTED */
  font-size: 12.5px;
}
.ds {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.ds-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}
.ds-live {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4a4944; /* mono.L[1]：Glance 的 LIVE 点 */
}
.ds-live-text {
  font-size: 11px;
  font-weight: 800;
  color: #1c1c1a; /* mono.INK */
  letter-spacing: 0.02em;
}
.ds-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 0 0 0 auto;
  padding: 0;
  list-style: none;
  font-size: 10.5px;
  color: #6a6963; /* mono.L[2] */
}
.ds-legend li {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.ds-legend i {
  width: 9px;
  height: 2.4px;
  border-radius: 1px;
}
.ds-legend b {
  color: #1c1c1a; /* mono.INK */
  font-variant-numeric: tabular-nums;
}
.ds-plot {
  flex: 1 1 auto;
  min-height: 0;
}
.ds-foot {
  margin: 2px 0 0;
  font-size: 10px;
  color: #8f8e88; /* mono.MUTED */
  line-height: 1.5;
}
/*
 * 减弱动效：这张图的动画在 ECharts 里，光靠 CSS 关不掉 ——
 * 组件已经用 `prefersReducedMotion()` 把 `animation` 置成 false（终态直接呈现），
 * 这里再兜一层：万一将来给 HTML 层加了过渡，也一并关掉。
 */
@media (prefers-reduced-motion: reduce) {
  .ds-live,
  .ds-plot,
  .ds-legend {
    animation: none;
    transition: none;
  }
}
</style>
