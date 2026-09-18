<script setup lang="ts">
import { computed } from 'vue'

import type { SingLineScore } from '@/api/m3-types'
import { computeLineTotal } from '@/composables/useSingScore'

const props = defineProps<{
  line: SingLineScore
  text?: string
  index?: number
}>()

const total = computed(() => computeLineTotal(props.line))

const dims = computed(() => [
  { key: 'pitch' as const, label: '音准', value: props.line.pitch },
  { key: 'rhythm' as const, label: '节奏', value: props.line.rhythm },
  { key: 'pronunciation' as const, label: '发音', value: props.line.pronunciation },
])
</script>

<template>
  <div class="rounded-[12px] border border-[#E5E7EB] bg-white p-4">
    <div class="mb-2 flex items-center justify-between">
      <span class="text-xs text-[#667085]">第 {{ (index ?? line.lineIndex) + 1 }} 句</span>
      <span class="text-sm font-bold text-score">{{ total }}</span>
    </div>
    <p v-if="text" class="mb-3 text-sm">{{ text }}</p>
    <div v-for="d in dims" :key="d.key" class="mb-2 last:mb-0">
      <div class="mb-1 flex justify-between text-xs">
        <span class="text-[#667085]">{{ d.label }}</span>
        <span class="font-semibold">{{ d.value }}</span>
      </div>
      <div class="h-1.5 overflow-hidden rounded-full bg-[#E5E7EB]">
        <div class="h-full rounded-full bg-score" :style="{ width: `${d.value}%` }" />
      </div>
    </div>
  </div>
</template>