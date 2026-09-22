<script setup lang="ts">
/**
 * 酒馆 · 动作面板（docs/56 §6）：贴底栏上方的快速行动条（遭遇战况 / 攻击 / 道具 / 建议行动）。
 *
 * 口径：**文本动作**（点按只发送台词，判定与状态由后端 DM 工具循环权威结算）——
 * - 攻击：先出小型确认（目标 + 可选武器，来自可用道具），确认后发「我攻击{目标}」；
 * - 道具：直接发「我使用{道具}」；
 * - 建议行动：观察/交谈/前进，直接发对应台词。
 * 遭遇进行中时顶部内嵌 TrpgEncounterCard（轮次/先攻序/HP）。
 */
import { computed, ref } from 'vue'

import IconFlask from '~icons/tabler/flask'
import IconSword from '~icons/tabler/sword'

import type {
  TavernEncounter,
  TavernItem,
  TavernParticipant,
} from '@/composables/useTavernEncounter'

import TrpgEncounterCard from './TrpgEncounterCard.vue'

const props = withDefaults(
  defineProps<{
    attackTargets?: TavernParticipant[]
    items?: TavernItem[]
    quickActions?: readonly { label: string; text: string }[]
    encounter?: TavernEncounter | null
    participants?: TavernParticipant[]
    disabled?: boolean
  }>(),
  {
    attackTargets: () => [],
    items: () => [],
    quickActions: () => [],
    encounter: null,
    participants: () => [],
    disabled: false,
  },
)

const emit = defineEmits<{ send: [text: string] }>()

/** 待确认的攻击目标（null = 无确认面板） */
const pendingTarget = ref<TavernParticipant | null>(null)
const weapon = ref('')

const weaponOptions = computed(() => props.items.map((item) => item.name))

function openAttack(target: TavernParticipant) {
  if (props.disabled) return
  pendingTarget.value = target
  weapon.value = ''
}

function confirmAttack() {
  const target = pendingTarget.value
  if (!target) return
  const line = weapon.value ? `我用${weapon.value}攻击${target.name}` : `我攻击${target.name}`
  pendingTarget.value = null
  weapon.value = ''
  emit('send', line)
}

function useItem(item: TavernItem) {
  if (props.disabled) return
  emit('send', `我使用${item.name}`)
}

function suggest(text: string) {
  if (props.disabled) return
  emit('send', text)
}
</script>

<template>
  <div class="t-act-panel" aria-label="快速行动">
    <TrpgEncounterCard
      v-if="props.encounter"
      :encounter="props.encounter"
      :participants="props.participants"
    />

    <div v-if="pendingTarget" class="t-act-confirm">
      <span class="t-act-confirm__ask">攻击 {{ pendingTarget.name }}</span>
      <select v-model="weapon" class="t-act-confirm__select" aria-label="选择武器">
        <option value="">徒手</option>
        <option v-for="name in weaponOptions" :key="name" :value="name">{{ name }}</option>
      </select>
      <button class="t-act-confirm__btn" type="button" @click="pendingTarget = null">取消</button>
      <button
        class="t-act-confirm__btn t-act-confirm__btn--go"
        type="button"
        :disabled="props.disabled"
        @click="confirmAttack"
      >
        确认攻击
      </button>
    </div>

    <div v-else class="t-act-panel__row">
      <span class="t-act-panel__label">⚡ 快速行动</span>
      <button
        v-for="target in props.attackTargets"
        :key="`atk-${target.key}`"
        class="t-act-chip t-act-chip--attack"
        type="button"
        :disabled="props.disabled"
        @click="openAttack(target)"
      >
        <IconSword />
        <span>攻击 {{ target.name }}</span>
        <span v-if="target.hp != null" class="t-act-chip__hp">HP {{ target.hp }}</span>
      </button>
      <button
        v-for="item in props.items"
        :key="`item-${item.name}`"
        class="t-act-chip t-act-chip--item"
        type="button"
        :disabled="props.disabled"
        :title="item.effect ?? undefined"
        @click="useItem(item)"
      >
        <IconFlask />
        <span>{{ item.name }} ×{{ item.qty }}</span>
      </button>
      <button
        v-for="action in props.quickActions"
        :key="`sug-${action.label}`"
        class="t-act-chip"
        type="button"
        :disabled="props.disabled"
        @click="suggest(action.text)"
      >
        {{ action.label }}
      </button>
    </div>
  </div>
</template>
