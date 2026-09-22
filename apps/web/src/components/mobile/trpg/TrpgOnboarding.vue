<script setup lang="ts">
/**
 * 酒馆 · 开局引导（迁移自 ai4u Onboarding，2026-09-21 扩场景卡）：
 * 无剧本时展示「开局三步」——选择场景卡开局（平台精选 + 我的卡）、自建剧本（名称 + 场景）；
 * 没有任何卡时回退到内置示例剧本「迷雾酒馆」。
 */
import { ref } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'

withDefaults(defineProps<{ busy?: boolean; hasCards?: boolean }>(), {
  busy: false,
  hasCards: false,
})

const emit = defineEmits<{
  'open-cards': []
  demo: []
  create: [payload: { name: string; scene: string }]
}>()

const name = ref('')
const scene = ref('')
const showForm = ref(false)

function submit() {
  emit('create', { name: name.value.trim() || '未命名剧本', scene: scene.value.trim() || '酒馆' })
}
</script>

<template>
  <section class="t-onboard">
    <div class="t-onboard__hero">
      <span class="t-onboard__badge">酒馆</span>
      <h1 class="t-onboard__title">开一局跑团</h1>
      <p class="t-onboard__sub">
        AI 担任主持人（DM）：你描述行动，它扮演 NPC、推进剧情；需要判定时由系统掷骰，状态与线索会一直被记住。
      </p>
    </div>

    <ol class="t-onboard__steps">
      <li><span>1</span>选一个剧本开局（或用示例剧本直接开玩）</li>
      <li><span>2</span>打字或用语音说出你的行动</li>
      <li><span>3</span>主持台里可查看事实表 / 任务线索 / 掷骰</li>
    </ol>

    <button
      class="u-btn u-btn--primary u-btn--block"
      type="button"
      :disabled="busy"
      @click="emit('open-cards')"
    >
      选择场景卡开局
    </button>
    <button
      v-if="!hasCards"
      class="u-btn u-btn--primary u-btn--block"
      type="button"
      :disabled="busy"
      @click="emit('demo')"
    >
      开始示例剧本「迷雾酒馆」
    </button>
    <button
      class="u-btn u-btn--secondary u-btn--block"
      type="button"
      :disabled="busy"
      @click="showForm = !showForm"
    >
      {{ showForm ? '收起自建' : '自建剧本' }}
    </button>

    <div v-if="showForm" class="t-onboard__form">
      <input v-model="name" class="text-input" placeholder="剧本名（如：迷雾酒馆）" aria-label="剧本名" maxlength="60">
      <input v-model="scene" class="text-input" placeholder="起始场景（如：酒馆）" aria-label="起始场景" maxlength="40">
      <button class="u-btn u-btn--primary u-btn--block" type="button" :disabled="busy" @click="submit">
        <MobileIcon name="play" :size="16" />
        开局
      </button>
    </div>
  </section>
</template>
