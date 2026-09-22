<script setup lang="ts">
/**
 * 酒馆 · 输入 dock（迁移自 ai4u ActionDock + 移动端自由对话输入栏）：
 * 快捷行动芯片（观察/交涉/攻击，发送固定中文行动）+ 文本输入 + 语音（ASR）+ 发送。
 * Enter 发送；处理中/录音中禁用；录音态显示提示。
 */
import { ref } from 'vue'

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
}>()

const text = ref('')

const QUICK_ACTIONS = ['我仔细观察四周', '我试着和店里的人搭话', '我握紧武器，准备应对']

function send() {
  const value = text.value.trim()
  if (!value || props.sending || props.recording) return
  text.value = ''
  emit('send', value)
}

function quick(action: string) {
  if (props.sending || props.recording) return
  emit('send', action)
}
</script>

<template>
  <div class="t-dock-wrap">
    <div v-if="recording" class="t-dock-state" role="status">
      聆听中… 点击 ■ 停止并发送（最长 {{ maxSeconds }} 秒）
    </div>
    <div class="t-quick">
      <button
        v-for="action in QUICK_ACTIONS"
        :key="action"
        class="t-quick__chip"
        type="button"
        :disabled="sending || recording"
        @click="quick(action)"
      >
        {{ action }}
      </button>
    </div>
    <div class="u-fc-bar">
      <input
        v-model="text"
        class="u-fc-input"
        type="text"
        placeholder="说一句你想做的事…"
        aria-label="酒馆输入"
        :disabled="sending || recording"
        maxlength="500"
        @keyup.enter="send"
      >
      <button
        class="u-fc-send"
        type="button"
        title="发送"
        aria-label="发送"
        :disabled="!text.trim() || sending || recording"
        @click="send"
      >
        <MobileIcon name="arrow" :size="20" />
      </button>
      <button
        class="u-fc-mic"
        :class="{ 'u-fc-mic--rec': recording }"
        type="button"
        :title="recording ? '停止录音' : '语音行动'"
        :aria-label="recording ? '停止录音' : '语音行动'"
        :disabled="sending"
        @click="emit('toggle-mic')"
      >
        <MobileIcon :name="recording ? 'stop' : 'mic'" :size="20" />
      </button>
    </div>
  </div>
</template>
