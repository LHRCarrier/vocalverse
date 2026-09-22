<script setup lang="ts">
/**
 * 酒馆 · 进度钟条（docs/56 §6）：任务名 + 分段刻度 + 当前/总格。
 * positive=琥珀/品牌色，threat=红调（倒计时）；满格 is-full 强调（DM 可结算）。
 * 纯展示：数据来自 useTavernQuest（事实 + quest 事件派生）；只渲染有钟的任务。
 */
import { computed } from 'vue'

import type { TavernQuest } from '@/composables/useTavernQuest'

const props = withDefaults(defineProps<{ quests?: TavernQuest[] }>(), { quests: () => [] })

/** 只显示真正的进度钟（仅 status 的任务行不进顶部条） */
const clocks = computed(() => props.quests.filter((q) => q.hasClock))

function pips(quest: TavernQuest): boolean[] {
  const total = Math.max(1, Math.min(12, quest.segments))
  return Array.from({ length: total }, (_, i) => i < quest.current)
}

function statusText(quest: TavernQuest): string {
  if (quest.status === 'done') return '已结算'
  if (quest.status === 'failed') return '已失败'
  return quest.full ? '满格·待结算' : quest.progress
}
</script>

<template>
  <div v-if="clocks.length" class="t-clocks" aria-label="任务进度">
    <div
      v-for="quest in clocks"
      :key="quest.name"
      class="t-clock"
      :class="[`t-clock--${quest.kind}`, { 'is-full': quest.full, 'is-closed': quest.status !== 'active' }]"
    >
      <span class="t-clock__name" :title="quest.name">{{ quest.name }}</span>
      <span class="t-clock__pips" aria-hidden="true">
        <span v-for="(lit, i) in pips(quest)" :key="i" class="t-clock__pip" :class="{ 'is-lit': lit }" />
      </span>
      <span class="t-clock__num">{{ statusText(quest) }}</span>
    </div>
  </div>
</template>
