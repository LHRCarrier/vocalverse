<script setup lang="ts">
/**
 * 酒馆 · 进度钟条（docs/56 §6 + docs/57 §3.2）：任务名（含 stage）+ 语义标签（威胁/推进）
 * + 分段刻度 + 状态；positive=琥珀/品牌色，threat=红调（倒计时）；满格 is-full 强调，
 * 文案玩家化（可收尾/已爆发）；tick 的 reason 有则显示。
 * 纯展示：数据来自 useTavernQuest（事实 + quest 事件派生）；只渲染有钟的任务。
 */
import { computed } from 'vue'

import IconHourglass from '~icons/tabler/hourglass'
import IconTarget from '~icons/tabler/target-arrow'

import type { TavernQuest } from '@/composables/useTavernQuest'

const props = withDefaults(defineProps<{ quests?: TavernQuest[] }>(), { quests: () => [] })

/** 只显示真正的进度钟（仅 status 的任务行不进顶部条） */
const clocks = computed(() => props.quests.filter((q) => q.hasClock))

function pips(quest: TavernQuest): boolean[] {
  const total = Math.max(1, Math.min(12, quest.segments))
  return Array.from({ length: total }, (_, i) => i < quest.current)
}

/** 玩家向状态文案（不再用主持台术语「满格·待结算」） */
function statusText(quest: TavernQuest): string {
  if (quest.status === 'done') return '已完结'
  if (quest.status === 'failed') return '已失败'
  if (quest.full) return quest.kind === 'threat' ? '已爆发' : '可收尾'
  return quest.progress
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
      <span class="t-clock__kind">
        <IconHourglass v-if="quest.kind === 'threat'" />
        <IconTarget v-else />
        <span>{{ quest.kind === 'threat' ? '威胁' : '推进' }}</span>
      </span>
      <span class="t-clock__name" :title="quest.name">
        {{ quest.name }}
        <span v-if="quest.stage" class="t-clock__stage">· {{ quest.stage }}</span>
      </span>
      <span class="t-clock__pips" aria-hidden="true">
        <span v-for="(lit, i) in pips(quest)" :key="i" class="t-clock__pip" :class="{ 'is-lit': lit }" />
      </span>
      <span class="t-clock__num">{{ statusText(quest) }}</span>
      <span v-if="quest.reason" class="t-clock__reason">{{ quest.reason }}</span>
    </div>
  </div>
</template>
