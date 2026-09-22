<script setup lang="ts">
/**
 * 酒馆 · 玩法视图（页内「酒馆跑团」tab 的内容区）。
 *
 * 从 MobileTavernView 拆出（fe-08 行数门禁；页面改为四视图导航后需要腾出行数）：
 * 副本任务卡（TrpgStageHeader）+ 消息正文流（TrpgMessageItem：DM 叙述/玩家/NPC 插片/系统卡）+
 * 流内状态提示。纯渲染层：消息操作、翻译、标注、立绘开合都由页面注入的 composable 承担。
 */
import { computed } from 'vue'

import type { TrpgState } from '@/api/trpg'
import type { TavernMarks } from '@/composables/useTavernMarks'
import type { TavernMessageActions } from '@/composables/useTavernMessageActions'
import type { TavernRow } from '@/composables/useTavernSession'
import type { TavernTranslations } from '@/composables/useTavernTranslations'

import MobileArt from '@/components/mobile/MobileArt.vue'

import TrpgMessageItem from './TrpgMessageItem.vue'
import TrpgStageHeader from './TrpgStageHeader.vue'

const props = withDefaults(
  defineProps<{
    state?: TrpgState | null
    rows?: TavernRow[]
    status?: 'idle' | 'busy' | 'error'
    statusHint?: string | null
    inputError?: string | null
    hp?: string | null
    location?: string | null
    inventory?: string | null
    activeTasks?: number
    danglingCount?: number
    goal?: string | null
    npcNames?: Set<string>
    avatarLetter?: string
    avatarUrl?: string | null
    userName?: string
    marks: TavernMarks
    translations: TavernTranslations
    msgActions: TavernMessageActions
  }>(),
  {
    state: null,
    rows: () => [],
    status: 'idle',
    statusHint: null,
    inputError: null,
    hp: null,
    location: null,
    inventory: null,
    activeTasks: 0,
    danglingCount: 0,
    goal: null,
    npcNames: () => new Set<string>(),
    avatarLetter: '我',
    avatarUrl: null,
    userName: '冒险者',
  },
)

const emit = defineEmits<{ 'open-standee': [hero: 'pc' | 'dm'] }>()

const campaignName = computed(() => props.state?.campaign.name ?? '')
const scene = computed(() => props.state?.scene ?? null)

function onStandee(role: 'user' | 'assistant') {
  emit('open-standee', role === 'user' ? 'pc' : 'dm')
}
</script>

<template>
  <TrpgStageHeader
    :campaign-name="campaignName"
    :scene="scene"
    :hp="props.hp"
    :location="props.location"
    :inventory="props.inventory"
    :active-tasks="props.activeTasks"
    :dangling-count="props.danglingCount"
    :goal="props.goal"
    :status="props.status"
  />

  <div class="t-log">
    <TrpgMessageItem
      v-for="(m, i) in props.rows"
      :key="i"
      :role="m.role"
      :kind="m.kind"
      :content="m.content"
      :payload="m.payload"
      :live="m.live"
      :npc-names="props.npcNames"
      :avatar-letter="props.avatarLetter"
      :avatar-url="props.avatarUrl"
      :user-name="props.userName"
      :marked="props.marks.has(m.content)"
      :active="props.msgActions.actionIndex.value === i"
      :translation="props.translations.stateFor(i)"
      :highlight="props.msgActions.highlightFor(i)"
      @actions="props.msgActions.open(i)"
      @translate="props.translations.toggle(i, m.content)"
      @standee="onStandee"
    />
    <div v-if="props.rows.length === 0" class="u-empty u-empty--center">
      <div class="u-empty__art"><MobileArt name="wave" :size="96" /></div>
      <div class="u-empty__sub">说一句话，DM 会接住你</div>
    </div>
    <div v-if="props.statusHint" class="t-status" role="status">{{ props.statusHint }}</div>
    <div v-if="props.inputError" class="u-error">{{ props.inputError }}</div>
  </div>
</template>
