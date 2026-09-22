<script setup lang="ts">
/**
 * 酒馆 · 角色立绘 / 档案展台（设计稿 local/跑团设计/tavern-redesign 的立绘抽屉）。
 *
 * 2026-09-22：顶部档案栏（DM / 冒险者切换）+ 装备特质条 + **设计稿全身立绘**（public/tavern/）
 * + 属性/行动面板。
 * **占位口径**：立绘为设计稿 AI 生成图（真实「文生图 → 挂实体档案」能力未实现，docs/54）；
 * 属性（STR/DEX/INT/WIS）系统未实现 → 四格为占位，展示真实的剧本/场景/线索/任务/行囊数据；
 * 「属性检定」= 现有 D20 桌骰（真实请求）。
 */
import { computed, ref, watch } from 'vue'

import type { TrpgFactItem } from '@/api/trpg'
import MobileIcon from '@/components/mobile/MobileIcon.vue'

import { TAVERN_ART, npcAvatar } from './art'

type Hero = 'dm' | 'pc' | 'npc'

const props = withDefaults(
  defineProps<{
    open: boolean
    campaignName: string
    scene?: string | null
    /** 玩家昵称（账号） */
    pcName: string
    tasks: number
    clues: number
    facts: TrpgFactItem[]
    npcs: string[]
    /** 打开时定位的档案页（消息头像/立绘链接传入） */
    initialHero?: Hero
    /** 任意 NPC 主角（docs/56 §6：点击在场角色条/立绘事件打开；无图时回退内置素材→首字） */
    npc?: { name: string; kind: string; portraitUrl?: string | null; note?: string | null } | null
  }>(),
  { scene: null, initialHero: 'dm', npc: null },
)

const emit = defineEmits<{ close: []; roll: [] }>()

const hero = ref<Hero>('dm')

watch(
  [() => props.open, () => props.npc],
  ([open]) => {
    if (!open) return
    hero.value = props.initialHero === 'npc' ? (props.npc ? 'npc' : 'dm') : props.initialHero
  },
)

const inventory = computed(  () => props.facts.find((f) => f.key.endsWith('.inventory'))?.value ?? null,
)
/** 行囊事实值 → 标签（中英文逗号/分号/顿号通吃） */
const inventoryTags = computed(() =>
  (inventory.value ?? '')
    .split(/[,;，；、]/)
    .map((s) => s.trim())
    .filter(Boolean),
)

const isDm = computed(() => hero.value === 'dm')
const isNpc = computed(() => hero.value === 'npc' && props.npc != null)
const heroName = computed(() =>
  isDm.value ? '守密人 (DM)' : isNpc.value ? (props.npc?.name ?? props.pcName) : props.pcName,
)
const heroRole = computed(() => {
  if (isDm.value) return '酒馆掌柜 · 规则仲裁者'
  if (isNpc.value) return props.npc?.kind === 'pc' ? '玩家角色 · 同行者' : '剧中人物 · NPC'
  return '冒险者 · 跑团主角'
})
/** NPC 立绘：实体挂图 → 内置素材（art.ts 按名字命中）→ null（组件用首字占位） */
const npcPortrait = computed(() => {
  const npc = props.npc
  if (!npc) return null
  return npc.portraitUrl || npcAvatar(npc.name)
})
const heroImg = computed(() => {
  if (isDm.value) return TAVERN_ART.dmStandee
  if (hero.value === 'pc') return TAVERN_ART.pcStandee
  return npcPortrait.value
})
const heroTraits = computed<string[]>(() => {
  if (isDm.value) {
    return [
      `📖 ${props.campaignName}`,
      props.scene ? `📍 ${props.scene}` : '📍 未定场景',
      `🗝 ${props.clues} 线索`,
      `⚔ ${props.tasks} 任务`,
      `👥 ${props.npcs.length} 人物`,
    ]
  }
  if (isNpc.value) {
    const kind = props.npc?.kind === 'pc' ? '同行者' : 'NPC'
    return [
      `📖 ${props.campaignName}`,
      props.scene ? `📍 ${props.scene}` : '📍 未定场景',
      `🎭 ${kind}`,
      ...(props.npc?.note ? [`📝 ${props.npc.note}`] : []),
    ]
  }
  return inventoryTags.value.length
    ? inventoryTags.value.map((t) => `🎒 ${t}`)
    : ['🎒 行囊待生成']
})
</script>

<template>
  <div v-if="props.open" class="t-sheet t-standee">
    <div class="t-sheet__backdrop" role="presentation" @click="emit('close')" />
    <section class="t-standee__panel" role="dialog" aria-label="角色立绘">
      <header class="t-standee__head">
        <span class="t-standee__title">📜 跑团角色立绘 · 档案展台</span>
        <button
          class="t-sheet__close"
          type="button"
          title="关闭"
          aria-label="关闭"
          @click="emit('close')"
        >
          <MobileIcon name="x" :size="18" />
        </button>
      </header>

      <div class="t-standee__meta">
        <div class="t-standee__who">
          <div class="t-standee__name">{{ heroName }}</div>
          <div class="t-standee__role">{{ heroRole }}</div>
        </div>
        <div class="t-standee__tabs" role="tablist" aria-label="档案切换">
          <button
            type="button"
            role="tab"
            :aria-selected="isDm"
            :class="{ 'is-on': isDm }"
            @click="hero = 'dm'"
          >
            DM 守密人
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="hero === 'pc'"
            :class="{ 'is-on': hero === 'pc' }"
            @click="hero = 'pc'"
          >
            冒险者 ({{ pcName }})
          </button>
          <button
            v-if="props.npc"
            type="button"
            role="tab"
            :aria-selected="isNpc"
            :class="{ 'is-on': isNpc }"
            @click="hero = 'npc'"
          >
            {{ props.npc.name }}
          </button>
        </div>
      </div>

      <div class="t-standee__traits">
        <span class="t-standee__traits-label">装备/特质:</span>
        <span v-for="t in heroTraits" :key="t" class="t-standee__trait">{{ t }}</span>
      </div>

      <div class="t-standee__stage">
        <img v-if="heroImg" class="t-standee__img" :src="heroImg" :alt="`${heroName} 立绘`">
        <div v-else class="t-standee__ph" aria-hidden="true">{{ heroName.slice(0, 1) }}</div>
      </div>

      <div class="t-standee__details">
        <div class="t-standee__stats">
          <div class="t-standee__stat">
            <div class="t-standee__stat-lbl">力量 STR</div>
            <div class="t-standee__stat-val">—</div>
          </div>
          <div class="t-standee__stat">
            <div class="t-standee__stat-lbl">敏捷 DEX</div>
            <div class="t-standee__stat-val">—</div>
          </div>
          <div class="t-standee__stat">
            <div class="t-standee__stat-lbl">智力 INT</div>
            <div class="t-standee__stat-val">—</div>
          </div>
          <div class="t-standee__stat">
            <div class="t-standee__stat-lbl">感知 WIS</div>
            <div class="t-standee__stat-val">—</div>
          </div>
        </div>
        <p class="t-standee__hint">
          立绘为设计稿占位图（生成能力见 docs/54）；属性系统后续开放（当前为占位），「属性检定」走现有 D20 桌骰。
        </p>
        <div class="t-standee__actions">
          <button class="t-standee__btn t-standee__btn--sec" type="button" @click="emit('roll')">
            🎲 属性检定
          </button>
          <button class="t-standee__btn t-standee__btn--pri" type="button" @click="emit('close')">
            ⚔️ 返回冒险对话
          </button>
        </div>
      </div>
    </section>
  </div>
</template>
