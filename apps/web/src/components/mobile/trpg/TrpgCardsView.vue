<script setup lang="ts">
/**
 * 酒馆 · 角色卡（页内「角色卡」tab 的内容区）。
 *
 * 玩家角色（PC 卡：立绘/HP/位置/行囊，行囊取 `pc.*.inventory` 事实，立绘回退内置素材）+
 * 在场人物（NPC：在场/赶来/已离场三段，关系事实 `rel.{名}.attitude|trust` 有则展示）+
 * 离场（置灰段）。点 NPC 卡开既有立绘展台（TrpgStandeeSheet，已支持 npc），点 PC 卡开 PC 页。
 * 数据来自 useTavernCast（members 已解析立绘与三态）与 state.facts，不发新请求。
 */
import { computed } from 'vue'

import IconHeartbeat from '~icons/tabler/heartbeat'
import IconMapPin from '~icons/tabler/map-pin'
import IconBackpack from '~icons/tabler/backpack'

import type { TrpgFactItem } from '@/api/trpg'
import type { TavernCastMember } from '@/composables/useTavernCast'
import { splitInventory } from '@/composables/useTavernEncounter'

import { TAVERN_ART } from './art'

const props = withDefaults(
  defineProps<{
    pcName?: string
    facts?: TrpgFactItem[]
    members?: TavernCastMember[]
  }>(),
  { pcName: '冒险者', facts: () => [], members: () => [] },
)

const emit = defineEmits<{ select: [member: TavernCastMember]; selectPc: [] }>()

const pcMember = computed(() => props.members.find((m) => m.kind === 'pc') ?? null)
const pcDisplayName = computed(() => pcMember.value?.name ?? props.pcName)
const pcPortrait = computed(() => pcMember.value?.portraitUrl ?? TAVERN_ART.pcAvatar)

/** PC 事实：先精确匹配当前名字，再退化为任意 `pc.*.{prop}`（旧场景卡没有实体名时的兜底） */
function pcFact(prop: string): string | null {
  const exact = props.facts.find((f) => f.key === `pc.${pcDisplayName.value}.${prop}`)
  if (exact) return exact.value
  return props.facts.find((f) => f.key.startsWith('pc.') && f.key.endsWith(`.${prop}`))?.value ?? null
}

const pcHp = computed(() => pcFact('hp'))
const pcLocation = computed(() => pcFact('location'))
const pcInventory = computed(() => splitInventory(pcFact('inventory')))

const npcs = computed(() => props.members.filter((m) => m.kind === 'npc'))
const present = computed(() => npcs.value.filter((m) => m.status === 'active'))
const arriving = computed(() => npcs.value.filter((m) => m.status === 'arriving'))
const departed = computed(() => npcs.value.filter((m) => m.status === 'departed'))

const STATUS_LABELS = { active: '在场', arriving: '赶来中', departed: '已离场' } as const
const REL_LABELS: Record<string, string> = { attitude: '态度', trust: '信任' }

/** 该 NPC 的关系事实（态度/信任等），无则空数组（不渲染关系行） */
function relations(member: TavernCastMember): string[] {
  const prefix = `rel.${member.name}.`
  return props.facts
    .filter((f) => f.key.startsWith(prefix))
    .map((f) => {
      const prop = f.key.slice(prefix.length)
      return `${REL_LABELS[prop] ?? prop}：${f.value}`
    })
}

const hasCast = computed(() => pcMember.value != null || npcs.value.length > 0)
/** PC 区只在有实体或事实时渲染（避免空局出现一张空卡） */
const hasPc = computed(
  () => pcMember.value != null || pcHp.value != null || pcLocation.value != null || pcInventory.value.length > 0,
)
</script>

<template>
  <div class="t-cards">
    <section v-if="hasPc" class="t-cards__sec">
      <h2 class="t-cards__title">玩家角色</h2>
      <button class="t-cards__pc" type="button" aria-label="查看我的角色卡" @click="emit('selectPc')">
        <img class="t-cards__pc-img" :src="pcPortrait" :alt="`${pcDisplayName} 立绘`">
        <span class="t-cards__pc-body">
          <span class="t-cards__pc-name">{{ pcDisplayName }}</span>
          <span class="t-cards__pc-rows">
            <span class="t-cards__fact"><IconHeartbeat /> HP {{ pcHp ?? '—' }}</span>
            <span class="t-cards__fact"><IconMapPin /> {{ pcLocation ?? '位置未知' }}</span>
          </span>
          <span class="t-cards__bag">
            <IconBackpack />
            <template v-if="pcInventory.length">
              <span v-for="item in pcInventory" :key="item" class="t-cards__bag-tag">{{ item }}</span>
            </template>
            <span v-else class="t-cards__bag-empty">行囊空空</span>
          </span>
        </span>
      </button>
    </section>

    <div v-if="!hasCast" class="u-empty u-empty--center">
      <div class="t-cards__empty-title">本局暂无人物档案</div>
      <div class="u-empty__sub">开局后 DM 会登记在场人物，这里会随剧情更新。</div>
    </div>

    <section v-if="present.length" class="t-cards__sec">
      <h2 class="t-cards__title">在场人物 <span class="t-cards__count">{{ present.length }}</span></h2>
      <div class="t-cards__grid">
        <button
          v-for="m in present"
          :key="m.name"
          class="t-cards__npc"
          type="button"
          :aria-label="`查看 ${m.name} 的角色卡`"
          @click="emit('select', m)"
        >
          <img v-if="m.portraitUrl" class="t-cards__npc-img" :src="m.portraitUrl" :alt="m.name">
          <span v-else class="t-cards__npc-ph" aria-hidden="true">{{ m.name.slice(0, 1) }}</span>
          <span class="t-cards__npc-name">{{ m.name }}</span>
          <span class="t-cards__npc-status" :class="`is-${m.status}`">{{ STATUS_LABELS[m.status] }}</span>
          <span v-for="rel in relations(m)" :key="rel" class="t-cards__rel">{{ rel }}</span>
        </button>
      </div>
    </section>

    <section v-if="arriving.length" class="t-cards__sec">
      <h2 class="t-cards__title">正在赶来 <span class="t-cards__count">{{ arriving.length }}</span></h2>
      <div class="t-cards__grid">
        <button
          v-for="m in arriving"
          :key="m.name"
          class="t-cards__npc is-arriving"
          type="button"
          :aria-label="`查看 ${m.name} 的角色卡`"
          @click="emit('select', m)"
        >
          <img v-if="m.portraitUrl" class="t-cards__npc-img" :src="m.portraitUrl" :alt="m.name">
          <span v-else class="t-cards__npc-ph" aria-hidden="true">{{ m.name.slice(0, 1) }}</span>
          <span class="t-cards__npc-name">{{ m.name }}</span>
          <span class="t-cards__npc-status is-arriving">{{ STATUS_LABELS.arriving }}</span>
          <span v-if="m.note" class="t-cards__rel">{{ m.note }}</span>
        </button>
      </div>
    </section>

    <section v-if="departed.length" class="t-cards__sec t-cards__sec--departed">
      <h2 class="t-cards__title">离场 <span class="t-cards__count">{{ departed.length }}</span></h2>
      <div class="t-cards__grid">
        <button
          v-for="m in departed"
          :key="m.name"
          class="t-cards__npc is-departed"
          type="button"
          :aria-label="`查看 ${m.name} 的角色卡`"
          @click="emit('select', m)"
        >
          <img v-if="m.portraitUrl" class="t-cards__npc-img" :src="m.portraitUrl" :alt="m.name">
          <span v-else class="t-cards__npc-ph" aria-hidden="true">{{ m.name.slice(0, 1) }}</span>
          <span class="t-cards__npc-name">{{ m.name }}</span>
          <span class="t-cards__npc-status is-departed">{{ STATUS_LABELS.departed }}</span>
        </button>
      </div>
    </section>
  </div>
</template>
