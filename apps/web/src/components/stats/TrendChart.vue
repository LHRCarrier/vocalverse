<script setup lang="ts">
import { ref } from 'vue'

import type { StatSeries } from '@/api/m3-types'
import { useECharts } from '@/composables/useECharts'
import { tokens } from '@/styles/tokens'

const props = defineProps<{ dates: string[]; series: StatSeries[] }>()

const el = ref<HTMLElement | null>(null)
const PALETTE = [tokens.colors.brand, tokens.colors.score, tokens.colors.info]

useECharts(el, () => ({
  tooltip: { trigger: 'axis' },
  legend: { bottom: 0, textStyle: { fontSize: 11 } },
  grid: { left: 36, right: 16, top: 20, bottom: 32 },
  xAxis: { type: 'category', data: props.dates, boundaryGap: false },
  yAxis: { type: 'value', max: 100 },
  series: props.series.map((s, i) => ({
    name: s.name,
    type: 'line' as const,
    smooth: true,
    data: s.values,
    lineStyle: { color: PALETTE[i % PALETTE.length], width: 2.5 },
    itemStyle: { color: PALETTE[i % PALETTE.length] },
  })),
}))
</script>

<template>
  <div ref="el" class="h-[260px] w-full" />
</template>