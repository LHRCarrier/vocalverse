<script setup lang="ts">
/**
 * 酒馆 · 消息项（迁移自 ai4u MessageItem）：
 * - 系统卡：open（开场重卡：剧本名/场景/任务）、scene（过场细线）、dice（判定卡，成功绿/失败红）；
 * - 玩家气泡（右｜炭黑）；DM 气泡（左｜白卡，NPC 台词按「名字：」渲染成人名标签段）。
 * 安全：全部文本插值（禁 v-html，docs/13 §5）；分段规则见 ./segments.ts。
 */
import { computed } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'

import { npcSegments } from './segments'

const props = withDefaults(
  defineProps<{
    role: 'user' | 'assistant'
    kind?: 'text' | 'system'
    content: string
    payload?: Record<string, unknown> | null
    /** 当前 AI 流式目标（尾部闪烁光标） */
    live?: boolean
    /** NPC 名单（实体表 kind=npc；决定「名字：」是否渲染成人名标签） */
    npcNames?: Set<string>
    avatarLetter?: string
    speakable?: boolean
    playing?: boolean
  }>(),
  {
    kind: 'text',
    payload: null,
    live: false,
    npcNames: () => new Set<string>(),
    avatarLetter: '我',
    speakable: false,
    playing: false,
  },
)

const emit = defineEmits<{ replay: [] }>()

const isSystem = computed(() => props.kind === 'system')
const sysType = computed(() => String(props.payload?.trpg_sys ?? ''))
const segments = computed(() => npcSegments(props.content, props.npcNames))

const scenePayload = computed(() => props.payload ?? {})
const openTasks = computed<string[]>(() => {
  const raw = scenePayload.value.tasks
  return Array.isArray(raw) ? raw.map((x) => String(x)) : []
})
const diceLines = computed(() => String(scenePayload.value.text ?? '').split('\n').filter(Boolean))
const diceOutcome = computed<'success' | 'failure' | null>(() => {
  const text = String(scenePayload.value.text ?? '')
  if (text.includes('成功')) return 'success'
  if (text.includes('失败')) return 'failure'
  return null
})
</script>

<template>
  <!-- 系统卡：开场 -->
  <section v-if="isSystem && sysType === 'open'" class="t-card t-card--open">
    <div class="t-card__kicker">冒险开始</div>
    <div class="t-card__title">{{ scenePayload.campaign_name ?? '无名剧本' }}</div>
    <div class="t-card__meta">
      <span v-if="scenePayload.scene">场景 · {{ scenePayload.scene }}</span>
      <span v-if="openTasks.length">任务 · {{ openTasks.join(' / ') }}</span>
    </div>
  </section>

  <!-- 系统卡：过场（细线） -->
  <div v-else-if="isSystem && sysType === 'scene'" class="t-scene-line">
    —— 场景 · {{ scenePayload.scene ?? '未知' }} ——
  </div>

  <!-- 系统卡：判定 -->
  <section
    v-else-if="isSystem && sysType === 'dice'"
    class="t-card t-card--dice"
    :class="diceOutcome === 'success' ? 'is-success' : diceOutcome === 'failure' ? 'is-fail' : ''"
  >
    <div class="t-card__dice-head">🎲 判定</div>
    <div v-for="(line, i) in diceLines" :key="i" class="t-card__dice-line">{{ line }}</div>
  </section>

  <!-- 未知系统卡：降级为文本（前向兼容） -->
  <div v-else-if="isSystem" class="t-scene-line">{{ content || `系统卡：${sysType}` }}</div>

  <!-- 气泡 -->
  <div v-else class="u-chat" :class="{ 'u-chat--user': role === 'user' }">
    <span v-if="role === 'assistant'" class="u-ava t-ava--dm" aria-hidden="true">
      <MobileIcon name="coffee" :size="16" />
    </span>
    <div class="u-bubble" :class="role === 'user' ? 'u-bubble--user' : 'u-bubble--ai'">
      <template v-if="role === 'assistant'">
        <p v-for="(seg, i) in segments" :key="i" class="t-seg" :class="{ 't-seg--npc': seg.npc }">
          <span v-if="seg.npc" class="t-seg__npc">{{ seg.npc }}</span>
          <span class="t-seg__text">{{ seg.text }}</span>
        </p>
        <span v-if="live" class="t-caret" aria-hidden="true">▍</span>
        <button
          v-if="speakable"
          class="u-replay"
          :class="{ 'is-playing': playing }"
          type="button"
          :title="playing ? '停止' : '重听'"
          :aria-label="playing ? '停止播放' : '重听语音'"
          @click="emit('replay')"
        >
          <template v-if="playing"><span class="u-eq" aria-hidden="true"><i /><i /><i /></span></template>
          <MobileIcon v-else name="volume" :size="20" />
        </button>
      </template>
      <template v-else>{{ content || '…' }}</template>
    </div>
    <span v-if="role === 'user'" class="u-ava u-ava--me" aria-hidden="true">{{ avatarLetter }}</span>
  </div>
</template>
