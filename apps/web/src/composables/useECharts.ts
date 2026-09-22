/**
 * ECharts 懒加载封装（docs/13 §4 / docs/06 §3）。
 *
 * - 全部按需注册（core/charts/components/renderers 动态 import），不进首屏 chunk；
 * - 组件卸载自动 dispose，ResizeObserver 自适应容器；
 * - 2026-09-21（docs/53 P2）：**首个消费者 = `/stats` 报表页**（趋势/雷达/四指标卡 + 导出）；
 *   新增 `setOption`（时间范围切换时原地更新）与 `getDataURL`（图表 PNG 导出）、RadarChart 注册。
 *   管理端图表仍是独立 SPA `apps/admin` 的 `components/charts/**`（自有 Mono token 层，不 import 本文件）。
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
    const { LineChart, PieChart, BarChart, RadarChart } = await import('echarts/charts')
    const {
      GridComponent,
      TooltipComponent,
      LegendComponent,
      TitleComponent,
      RadarComponent,
    } = await import('echarts/components')
    const { CanvasRenderer } = await import('echarts/renderers')
    echarts.use([
      LineChart,
      PieChart,
      BarChart,
      RadarChart,
      GridComponent,
      TooltipComponent,
      LegendComponent,
      TitleComponent,
      RadarComponent,
      CanvasRenderer,
    ])
    chart = echarts.init(node)
    chart.setOption(getOption())
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(node)
  }

  /** 原地更新（时间范围切换等；图表未就绪时静默——挂载后会走 getOption） */
  function setOption(option: EChartsOption): void {
    chart?.setOption(option, { notMerge: true })
  }

  /** 图表 PNG（导出用；未就绪返回空串） */
  function getDataURL(): string {
    return chart?.getDataURL({ pixelRatio: 2, backgroundColor: '#ffffff' }) ?? ''
  }

  onMounted(init)
  onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
    chart?.dispose()
    chart = null
  })

  return { setOption, getDataURL }
}
