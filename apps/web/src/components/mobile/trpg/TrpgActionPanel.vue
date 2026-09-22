<script setup lang="ts">
/**
 * 酒馆 · 动作面板（docs/56 §6 + docs/57 §3.2）：
 *
 * - **常驻**：无实体/无道具时也给通用行动（观察/交谈/前进）；
 * - 单行 chip：攻击（仅遭遇激活时由页面传入）/ 道具 / 情境建议 / 收尾；
 *   横滑 + 两侧渐隐（CSS），点按行为：
 *   - 情境建议 → 只填入输入框（`prefill`，与旧 dock「推荐行动」合并为一排）；
 *   - 道具 → 直接发「我使用{道具}」+ 即时回执（`feedback` toast）；
 *   - 攻击 → 二次确认（武器下拉排除消耗品/治疗品）→ 发送 + 回执；
 *   - 收尾本幕 → 页面调确定性结算接口。
 * 遭遇进行中时顶部内嵌 TrpgEncounterCard（轮次/先攻序/HP）。
 */
import { computed, ref } from 'vue'

import IconFlask from '~icons/tabler/flask'
import IconSword from '~icons/tabler/sword'
import IconFlag from '~icons/tabler/flag-check'

import type { TavernQuickAction } from '@/composables/useTavernSuggestions'
import type { TavernEncounter, TavernItem, TavernParticipant } from '@/composables/useTavernEncounter'
import { isWeapon } from '@/composables/useTavernEncounter'

import TrpgEncounterCard from './TrpgEncounterCard.vue'

const props = withDefaults(
  defineProps<{
    attackTargets?: TavernParticipant[]
    items?: TavernItem[]
    quickActions?: readonly TavernQuickAction[]
    encounter?: TavernEncounter | null
    participants?: TavernParticipant[]
    /** 满格、可收尾的进行中任务（页面过滤后传入；空 = 不渲染收尾钮） */
    settleable?: readonly { name: string }[]
    disabled?: boolean
    settling?: boolean
  }>(),
  {
    attackTargets: () => [],
    items: () => [],
    quickActions: () => [],
    encounter: null,
    participants: () => [],
    settleable: () => [],
    disabled: false,
    settling: false,
  },
)

const emit = defineEmits<{
  send: [text: string]
  prefill: [text: string]
  feedback: [message: string]
  settle: [quest: string]
}>()

/** 待确认的攻击目标（null = 无确认面板） */
const pendingTarget = ref<TavernParticipant | null>(null)
const weapon = ref('')

/** 武器候选：排除消耗品与治疗类道具（药水不能当武器） */
const weaponOptions = computed(() => props.items.filter(isWeapon).map((item) => item.name))

const canAct = computed(() => !props.disabled)

function openAttack(target: TavernParticipant) {
  if (!canAct.value) return
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
  emit('feedback', `已出手 · ${line}`)
}

function useItem(item: TavernItem) {
  if (!canAct.value) return
  const line = `我使用${item.name}`
  emit('send', line)
  emit('feedback', `已使用 · ${item.name}`)
}

function suggest(text: string) {
  if (!canAct.value) return
  emit('prefill', text)
}

function settle(quest: string) {
  if (!canAct.value || props.settling) return
  emit('settle', quest)
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
      <span class="t-act-panel__label" aria-hidden="true">⚡ 行动</span>
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
        <span>{{ item.name }}<template v-if="item.qty > 1"> ×{{ item.qty }}</template></span>
      </button>
      <button
        v-for="quest in props.settleable"
        :key="`settle-${quest.name}`"
        class="t-act-chip t-act-chip--settle"
        type="button"
        :disabled="props.disabled || props.settling"
        @click="settle(quest.name)"
      >
        <IconFlag />
        <span>收尾本幕 · {{ quest.name }}</span>
      </button>
      <button
        v-for="action in props.quickActions"
        :key="`sug-${action.kind}-${action.label}`"
        class="t-act-chip t-act-chip--suggest"
        type="button"
        :disabled="props.disabled"
        @click="suggest(action.text)"
      >
        {{ action.label }}
      </button>
    </div>
  </div>
</template>
