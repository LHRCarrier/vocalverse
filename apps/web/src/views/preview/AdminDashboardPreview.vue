<script setup lang="ts">
import { ref } from 'vue'
import { NTag } from 'naive-ui'

import { useECharts } from '@/composables/useECharts'

/** 管理端门面（docs/13 §5）：4 指标卡 + 趋势 + 分布 + 热度，全部 ECharts 按需注册、懒加载。 */
const metrics = [
  { label: '点击率 CTR', value: '12.5%', delta: '↑ 1.2pt', up: true },
  { label: '完成率', value: '68.4%', delta: '↑ 5.1pt', up: true },
  { label: '互动率', value: '42.1%', delta: '↓ 0.8pt', up: false },
  { label: '跳出率', value: '31.2%', delta: '↓ 3.4pt', up: true },
]

const trendEl = ref<HTMLElement | null>(null)
const distEl = ref<HTMLElement | null>(null)
const heatEl = ref<HTMLElement | null>(null)

useECharts(trendEl, () => ({
  title: { text: '7 日练习完成率', textStyle: { fontSize: 13 } },
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 16, top: 36, bottom: 24 },
  xAxis: { type: 'category', data: ['08-25', '08-26', '08-27', '08-28', '08-29', '08-30', '08-31'] },
  yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
  series: [
    {
      type: 'line',
      smooth: true,
      data: [52, 61, 58, 66, 63, 71, 68.4],
      areaStyle: { color: '#22C55E', opacity: 0.12 },
      lineStyle: { color: '#16A34A', width: 3 },
      itemStyle: { color: '#16A34A' },
    },
  ],
}))

useECharts(distEl, () => ({
  title: { text: '用户水平分布', textStyle: { fontSize: 13 } },
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [
    {
      type: 'pie',
      radius: ['42%', '68%'],
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: { formatter: '{b} {c}%' },
      data: [
        { value: 18, name: 'L1', itemStyle: { color: '#F87171' } },
        { value: 34, name: 'L2', itemStyle: { color: '#FB923C' } },
        { value: 31, name: 'L3', itemStyle: { color: '#22C55E' } },
        { value: 17, name: 'L4', itemStyle: { color: '#0EA5E9' } },
      ],
    },
  ],
}))

useECharts(heatEl, () => ({
  title: { text: '场景热度（练习会话数）', textStyle: { fontSize: 13 } },
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 16, top: 36, bottom: 24 },
  xAxis: { type: 'category', data: ['咖啡馆', '机场', '面试', '图书馆'] },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'bar',
      barWidth: 26,
      itemStyle: { color: '#16A34A', borderRadius: [8, 8, 0, 0] },
      data: [420, 286, 351, 198],
    },
  ],
}))
</script>

<template>
  <div>
    <header class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold">评价看板</h1>
        <p class="text-sm text-[#667085]">四指标口径 docs/06 §9.1 · M3 接入真实埋点</p>
      </div>
      <NTag round :bordered="false" :color="{ color: '#ECFDF5', textColor: '#15803D' }">DEMO 数据</NTag>
    </header>

    <!-- 指标卡 -->
    <section class="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
      <article
        v-for="m in metrics"
        :key="m.label"
        class="rounded-[12px] border border-[#E5E7EB] bg-white p-4"
      >
        <p class="mb-1 text-xs text-[#667085]">{{ m.label }}</p>
        <p class="mb-2 text-2xl font-bold">{{ m.value }}</p>
        <p class="text-xs font-semibold" :class="m.up ? 'text-brand-deep' : 'text-[#EF4444]'">
          {{ m.delta }}
        </p>
      </article>
    </section>

    <!-- 图表区 -->
    <section class="grid grid-cols-1 gap-4 md:grid-cols-2">
      <div ref="trendEl" class="h-[260px] rounded-[12px] border border-[#E5E7EB] bg-white p-2" />
      <div ref="distEl" class="h-[260px] rounded-[12px] border border-[#E5E7EB] bg-white p-2" />
      <div ref="heatEl" class="h-[260px] rounded-[12px] border border-[#E5E7EB] bg-white p-2 md:col-span-2" />
    </section>
  </div>
</template>
