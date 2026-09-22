<script setup lang="ts">
/**
 * 酒馆 · 输入 dock（2026-09-22 按设计稿 dock-control 改版）：
 * - 推荐行动 chips：**点击快速填入输入框**（设计稿行为，不再直接发送）；
 * - 输入条：骰钮（快速投骰 D20）+ 文本 + 语音（ASR）+ 发送；
 * - Enter 发送；处理中/录音中禁用；录音态显示提示。语音链路（录音→ASR→逐句 TTS）原样保留。
 */
import { ref } from 'vue'

import IconCube from '~icons/tabler/cube'
import IconSend from '~icons/tabler/send'

import MobileIcon from '@/components/mobile/MobileIcon.vue'

const props = withDefaults(
  defineProps<{
    sending?: boolean
    recording?: boolean
    /** 语音输入上限（秒），提示文案用 */
    maxSeconds?: number
  }>(),
  { sending: false, recording: false, maxSeconds: 30 },
)

const emit = defineEmits<{
  send: [text: string]
  'toggle-mic': []
  roll: []
}>()

const text = ref('')
const inputEl = ref<HTMLInputElement | null>(null)

const QUICK_ACTIONS = [
  { icon: '👁️', label: '观察四周', action: '我仔细观察四周' },
  { icon: '💬', label: '找人搭话', action: '我试着和店里的人搭话' },
  { icon: '⚔️', label: '握紧武器', action: '我握紧武器，准备应对' },
]

function fill(action: string) {
  if (props.sending || props.recording) return
  text.value = action
  inputEl.value?.focus()
}

function send() {
  const value = text.value.trim()
  if (!value || props.sending || props.recording) return
  text.value = ''
  emit('send', value)
}
</script>

<template>
  <div class="t-dock-wrap">
    <div v-if="recording" class="t-dock-state" role="status">
      聆听中… 点击 ■ 停止并发送（最长 {{ maxSeconds }} 秒）
    </div>

    <div class="t-quick">
      <div class="t-quick__label">
        <span>⚡ 推荐行动</span>
        <span class="t-quick__hint">点击快速填入</span>
      </div>
      <div class="t-quick__row">
        <button
          v-for="item in QUICK_ACTIONS"
          :key="item.action"
          class="t-quick__chip"
          type="button"
          :disabled="sending || recording"
          @click="fill(item.action)"
        >
          <span aria-hidden="true">{{ item.icon }}</span>
          {{ item.label }}
        </button>
      </div>
    </div>

    <div class="t-input-bar">
      <button
        class="t-input-bar__btn t-input-bar__btn--dice"
        type="button"
        title="快速投骰 D20"
        aria-label="快速投骰 D20"
        :disabled="sending || recording"
        @click="emit('roll')"
      >
        <IconCube />
      </button>
      <input
        ref="inputEl"
        v-model="text"
        class="t-input-bar__input"
        type="text"
        placeholder="输入你想做的事，或点骰子掷骰…"
        aria-label="酒馆输入"
        :disabled="sending || recording"
        maxlength="500"
        @keyup.enter="send"
      >
      <button
        class="t-input-bar__btn"
        :class="{ 'is-rec': recording }"
        type="button"
        :title="recording ? '停止录音' : '语音行动'"
        :aria-label="recording ? '停止录音' : '语音行动'"
        :disabled="sending"
        @click="emit('toggle-mic')"
      >
        <MobileIcon :name="recording ? 'stop' : 'mic'" :size="20" />
      </button>
      <button
        class="t-input-bar__send"
        type="button"
        title="发送"
        aria-label="发送"
        :disabled="!text.trim() || sending || recording"
        @click="send"
      >
        <IconSend />
      </button>
    </div>
  </div>
</template>
