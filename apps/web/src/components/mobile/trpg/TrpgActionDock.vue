<script setup lang="ts">
/**
 * 酒馆 · 输入 dock（2026-09-22 按设计稿 dock-control 改版；2026-09-22 晚 docs/57 §3.2）：
 * - 只保留输入职责：骰钮（快速投骰 D20）+ 文本 + 语音（ASR）+ 发送；
 *   「推荐行动」相关 chip 已合并到 TrpgActionPanel（全站只有一排建议行动）；
 * - `prefill`：动作面板点建议 chips 时由页面注入台词（填入 + 聚焦，不直接发送）；
 * - Enter 发送；处理中/录音中禁用；录音态显示提示。语音链路（录音→ASR→逐句 TTS）原样保留。
 */
import { ref, watch } from 'vue'

import IconCube from '~icons/tabler/cube'
import IconSend from '~icons/tabler/send'

import MobileIcon from '@/components/mobile/MobileIcon.vue'

const props = withDefaults(
  defineProps<{
    sending?: boolean
    recording?: boolean
    /** 语音输入上限（秒），提示文案用 */
    maxSeconds?: number
    /** 外部注入的填入请求（seq 递增以重复触发同一文案） */
    prefill?: { text: string; seq: number } | null
  }>(),
  { sending: false, recording: false, maxSeconds: 30, prefill: null },
)

const emit = defineEmits<{
  send: [text: string]
  'toggle-mic': []
  roll: []
}>()

const text = ref('')
const inputEl = ref<HTMLInputElement | null>(null)

watch(
  () => props.prefill?.seq,
  () => {
    const incoming = props.prefill?.text
    if (!incoming || props.sending || props.recording) return
    text.value = incoming
    inputEl.value?.focus()
  },
)

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
