/**
 * ECharts 懒加载封装（docs/13 §4 / docs/06 §3）。
 *
 * - 全部按需注册（core/charts/components/renderers 动态 import），不进首屏 chunk；
 * - 组件卸载自动 dispose，ResizeObserver 自适应容器；
 * - ⚠️ 当前**在 apps/web 内无消费者**（2026-09-10）：原先唯一的示例页
 *   `views/preview/AdminDashboardPreview.vue` 属**已废弃的旧管理端**，已随 `/admin` 路由一并删除。
 *   管理端图表现在是独立 SPA `apps/admin` 的 `components/charts/**`（自有 Mono token 层，不 import 本文件）。
 *   本文件与 `echarts` 依赖**保留**供 M3 报表 / 学习画像（docs/36）使用；若到 M3 仍未使用，则连依赖一起删。
 */
import type { Ref } from 'vue'
import { onBeforeUnmount, onMounted } from 'vue'

import type { EChartsOption } from 'echarts'

type EChartsType = import('echarts/core').EChartsType

export function useECharts(el: Ref<HTMLElement | null>, getOption: () => EChartsOption) {
  let chart: EChartsType | null = null
  let observer: ResizeObserver | null = null

  async function init() {
    const node = el.value
    if (!node) return
    const echarts = await import('echarts/core')
    const { LineChart, PieChart, BarChart } = await import('echarts/charts')
    const {
      GridComponent,
      TooltipComponent,
      LegendComponent,
      TitleComponent,
    } = await import('echarts/components')
    const { CanvasRenderer } = await import('echarts/renderers')
    echarts.use([
      LineChart,
      PieChart,
      BarChart,
      GridComponent,
      TooltipComponent,
      LegendComponent,
      TitleComponent,
      CanvasRenderer,
    ])
    chart = echarts.init(node)
    chart.setOption(getOption())
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(node)
  }

  onMounted(init)
  onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
    chart?.dispose()
    chart = null
  })
}
