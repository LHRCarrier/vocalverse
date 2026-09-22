<script setup lang="ts">
/**
 * 酒馆 · 常驻迷你状态条（docs/57 §3.2「把状态搬进玩家视线」，VN-HUD 口径：小、可忽略、开箱即见）：
 *
 * dock 上方一行，折叠态：主任务名 + 进度格 + 「威胁/推进」文字标签 / 在场与赶来人数 / 线索入口。
 * - 点任务或箭头 → 展开完整钟条 + 在场角色条（`toggle`）；
 * - 点线索 → 主持台「任务线索」页（`open-console`）；
 * - 已结算任务不进条（只取 `status=active`）。
 */
import { computed } from 'vue'

import IconChevronDown from '~icons/tabler/chevron-down'
import IconChevronUp from '~icons/tabler/chevron-up'
import IconHourglass from '~icons/tabler/hourglass'
import IconKey from '~icons/tabler/key'
import IconTarget from '~icons/tabler/target-arrow'
import IconUsers from '~icons/tabler/users'

import type { TavernQuest } from '@/composables/useTavernQuest'

const props = withDefaults(
  defineProps<{
    quests?: TavernQuest[]
    presentCount?: number
    arrivingCount?: number
    clueCount?: number
    expanded?: boolean
  }>(),
  { quests: () => [], presentCount: 0, arrivingCount: 0, clueCount: 0, expanded: false },
)

const emit = defineEmits<{ toggle: []; 'open-console': [tab: 'quests'] }>()

/** 主任务：进行中的威胁钟优先（最紧迫），其次任意进行中钟，再退化为无钟任务 */
const primary = computed<TavernQuest | null>(() => {
  const active = props.quests.filter((q) => q.status === 'active')
  return (
    active.find((q) => q.hasClock && q.kind === 'threat') ??
    active.find((q) => q.hasClock) ??
    active[0] ??
    null
  )
})

const kindLabel = computed(() => (primary.value?.kind === 'threat' ? '威胁' : '推进'))

/** 折叠态文案：满格给玩家语言（可收尾/已爆发），平时显示 n/m */
const progressText = computed(() => {
  const quest = primary.value
  if (!quest) return '—'
  if (quest.status === 'done') return '已完结'
  if (quest.status === 'failed') return '已失败'
  if (quest.full) return quest.kind === 'threat' ? '已爆发' : '可收尾'
  return quest.progress
})

function pips(quest: TavernQuest): boolean[] {
  const total = Math.max(1, Math.min(12, quest.segments))
  return Array.from({ length: total }, (_, i) => i < quest.current)
}

const castText = computed(() =>
  props.arrivingCount > 0
    ? `在场 ${props.presentCount} · 赶来 ${props.arrivingCount}`
    : `在场 ${props.presentCount}`,
)
</script>

<template>
  <div class="t-mini" :class="{ 'is-open': props.expanded }" aria-label="本局状态">
    <button
      class="t-mini__quest"
      type="button"
      :aria-label="primary ? `任务：${primary.name}（${kindLabel}）` : '暂无线索任务'"
      @click="emit('toggle')"
    >
      <span class="t-mini__kind" :class="primary?.kind === 'threat' ? 'is-threat' : 'is-positive'">
        <IconHourglass v-if="primary?.kind === 'threat'" />
        <IconTarget v-else />
        <span>{{ primary ? kindLabel : '任务' }}</span>
      </span>
      <span class="t-mini__name">{{ primary?.name ?? '尚无目标' }}</span>
      <span v-if="primary?.hasClock" class="t-mini__pips" aria-hidden="true">
        <span v-for="(lit, i) in pips(primary)" :key="i" class="t-mini__pip" :class="{ 'is-lit': lit }" />
      </span>
      <span class="t-mini__num" :class="{ 'is-full': primary?.full }">{{ progressText }}</span>
    </button>

    <button class="t-mini__cast" type="button" :aria-label="castText" @click="emit('toggle')">
      <IconUsers />
      <span>{{ castText }}</span>
    </button>

    <button
      class="t-mini__clue"
      type="button"
      aria-label="线索与任务"
      @click="emit('open-console', 'quests')"
    >
      <IconKey />
      <span>{{ props.clueCount }}</span>
    </button>

    <button
      class="t-mini__caret"
      type="button"
      :aria-expanded="props.expanded"
      :aria-label="props.expanded ? '收起状态条' : '展开状态条'"
      @click="emit('toggle')"
    >
      <IconChevronDown v-if="props.expanded" />
      <IconChevronUp v-else />
    </button>
  </div>
</template>
