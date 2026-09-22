<script setup lang="ts">
import { ref } from 'vue'

import { useECharts } from '@/composables/useECharts'
import { tokens } from '@/styles/tokens'

const props = defineProps<{ dimensions: string[]; values: number[] }>()

const el = ref<HTMLElement | null>(null)

useECharts(el, () => ({
  tooltip: {},
  radar: {
    indicator: props.dimensions.map((name) => ({ name, max: 100 })),
    radius: '65%',
  },
  series: [
    {
      type: 'radar' as const,
      data: [
        {
          value: props.values,
          name: '当前水平',
          areaStyle: { color: tokens.colors.brand, opacity: 0.2 },
          lineStyle: { color: tokens.colors.brand, width: 2 },
          itemStyle: { color: tokens.colors.brand },
        },
      ],
    },
  ],
}))
</script>

<template>
  <div ref="el" class="h-[280px] w-full" />
</template>