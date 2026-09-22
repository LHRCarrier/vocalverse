<script setup lang="ts">
import { computed } from 'vue'

import type { MetricBoard } from '@/api/m3-types'

const props = defineProps<{ metrics: MetricBoard }>()

const items = computed(() => [
  { label: '点击率 CTR', value: props.metrics.ctr },
  { label: '完成率', value: props.metrics.completion },
  { label: '互动率', value: props.metrics.interaction },
  { label: '跳出率', value: props.metrics.bounce },
])
</script>

<template>
  <section class="grid grid-cols-2 gap-4 md:grid-cols-4">
    <article
      v-for="m in items"
      :key="m.label"
      class="rounded-[12px] border border-[#E5E7EB] bg-white p-4"
    >
      <p class="mb-1 text-xs text-[#667085]">{{ m.label }}</p>
      <p class="text-2xl font-bold">{{ m.value }}%</p>
    </article>
  </section>
</template>