/**
 * ECharts 懒加载封装（docs/13 §4 / docs/06 §3）。
 *
 * - 全部按需注册（core/charts/components/renderers 动态 import），不进首屏 chunk；
 * - 组件卸载自动 dispose，ResizeObserver 自适应容器；
 * - 使用示例见 AdminDashboardPreview.vue。
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
