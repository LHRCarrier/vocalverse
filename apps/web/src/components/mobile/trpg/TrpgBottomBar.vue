<script setup lang="ts">
/**
 * 酒馆 · 底部控制区（设计稿 dock-control + bottom-nav 一体的页脚；docs/57 §3.2 起兼作 dock 状态区）：
 *
 * 自上而下：已完结条 → 展开的完整钟条/在场条 → 动作面板（常驻单行）→ 迷你状态条 → 输入 dock → 页内导航。
 * 数据由页面注入；交互事件上抛（发送/填入/回执/结算/展开/开主持台/点角色）。
 * 沉浸页：全局底栏已移出（MobileTabBar group=null），本区贴 .u-phone 底边。
 */
import { computed } from 'vue'

import type { TavernCastMember } from '@/composables/useTavernCast'
import type {
  TavernEncounter,
  TavernItem,
  TavernParticipant,
} from '@/composables/useTavernEncounter'
import type { TavernQuest } from '@/composables/useTavernQuest'
import type { TavernQuickAction } from '@/composables/useTavernSuggestions'
import { useUiStore } from '@/stores/ui'

import TrpgActionDock from './TrpgActionDock.vue'
import TrpgActionPanel from './TrpgActionPanel.vue'
import TrpgCastBar from './TrpgCastBar.vue'
import TrpgGameNav from './TrpgGameNav.vue'
import TrpgMiniStrip from './TrpgMiniStrip.vue'
import TrpgQuestBar from './TrpgQuestBar.vue'

const props = withDefaults(
  defineProps<{
    sending: boolean
    recording: boolean
    /** 动作面板 → 输入框的填入请求 */
    prefill?: { text: string; seq: number } | null
    /** 本局已完结（显示「已完结」条 + 开新篇章） */
    finished?: boolean
    /** 迷你条展开态（展开完整钟条 + 在场条） */
    stripExpanded?: boolean
    quests?: TavernQuest[]
    castMembers?: TavernCastMember[]
    presentCount?: number
    arrivingCount?: number
    clueCount?: number
    attackTargets?: TavernParticipant[]
    items?: TavernItem[]
    quickActions?: readonly TavernQuickAction[]
    encounter?: TavernEncounter | null
    participants?: TavernParticipant[]
    /** 满格可收尾任务（页面过滤后传入） */
    settleable?: readonly { name: string }[]
    settling?: boolean
    disabled?: boolean
  }>(),
  {
    prefill: null,
    finished: false,
    stripExpanded: false,
    quests: () => [],
    castMembers: () => [],
    presentCount: 0,
    arrivingCount: 0,
    clueCount: 0,
    attackTargets: () => [],
    items: () => [],
    quickActions: () => [],
    encounter: null,
    participants: () => [],
    settleable: () => [],
    settling: false,
    disabled: false,
  },
)

const emit = defineEmits<{
  send: [text: string]
  'toggle-mic': []
  roll: []
  prefill: [text: string]
  feedback: [message: string]
  settle: [quest: string]
  'toggle-strip': []
  'open-console': [tab: 'quests']
  'cast-select': [member: TavernCastMember]
  'new-chapter': []
}>()

const ui = useUiStore()
const NAV_LABELS = { hall: '大堂', card: '角色卡', chronicle: '纪事' } as const

/** 攻击 chip 只在遭遇激活（DM 宣告战斗）时出现；已离场实体不列出（含 SSE 离场增量） */
const combatTargets = computed(() => {
  if (!props.encounter) return []
  const departed = new Set(props.castMembers.filter((m) => m.status === 'departed').map((m) => m.name))
  return props.attackTargets.filter((t) => !departed.has(t.name))
})

function onNav(key: 'hall' | 'tavern' | 'card' | 'chronicle') {
  if (key === 'tavern') {
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'smooth' })
    return
  }
  ui.showToast(`「${NAV_LABELS[key]}」后续版本开放`)
}
</script>

<template>
  <div class="u-chat-dock">
    <div v-if="props.finished" class="t-finished" role="status">
      <span class="t-finished__text">📖 本局已完结</span>
      <button class="t-finished__btn" type="button" @click="emit('new-chapter')">开新篇章</button>
    </div>

    <template v-if="props.stripExpanded">
      <TrpgQuestBar :quests="props.quests" />
      <TrpgCastBar :members="props.castMembers" @select="emit('cast-select', $event)" />
    </template>

    <TrpgActionPanel
      :attack-targets="combatTargets"
      :items="props.items"
      :quick-actions="props.quickActions"
      :encounter="props.encounter"
      :participants="props.participants"
      :settleable="props.settleable"
      :disabled="props.disabled"
      :settling="props.settling"
      @send="emit('send', $event)"
      @prefill="emit('prefill', $event)"
      @feedback="emit('feedback', $event)"
      @settle="emit('settle', $event)"
    />

    <TrpgMiniStrip
      :quests="props.quests"
      :present-count="props.presentCount"
      :arriving-count="props.arrivingCount"
      :clue-count="props.clueCount"
      :expanded="props.stripExpanded"
      @toggle="emit('toggle-strip')"
      @open-console="emit('open-console', $event)"
    />

    <TrpgActionDock
      :sending="props.sending"
      :recording="props.recording"
      :max-seconds="30"
      :prefill="props.prefill"
      @send="emit('send', $event)"
      @toggle-mic="emit('toggle-mic')"
      @roll="emit('roll')"
    />
  </div>
  <TrpgGameNav @nav="onNav" />
</template>
