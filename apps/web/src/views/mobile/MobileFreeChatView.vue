<script setup lang="ts">
/**
 * 移动端 · 自由对话（口语 = 场景对话 + 自由对话，docs/14 §12；2026-09-05）
 *
 * MVP 无状态：客户端自带滚动 history（≤24 条）交给后端 LLM 转发器；刷新即失忆；
 * 输入 = 麦克风（ASR）或打字，输出 = 流式文本 + 回合结束后 TTS 自动播报（可点喇叭重听）。
 * 不做评分/报告/入库（分期见 docs/14 §12）。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { track } from '@/api/events'
import { streamFreeChat, tts, type FreeChatMsg } from '@/api/practice'
import type { SseStreamEvent } from '@/audio/sse-types'
import { VoiceRecorder, MIN_RECORD_MS, micErrorMessage } from '@/audio/recorder'

import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import '@/styles/mobile-uic.css'

interface Bubble {
  role: 'assistant' | 'user'
  text: string
  /** 有可播语音（喇叭按钮出现条件；回合语音就绪即启用） */
  speakable?: boolean
}

/* 回复语速档位（后端 /api/v1/tts 已支持 rate 参数；本地记忆，2026-09-05 Grok 式功能行） */
const RATE_CYCLE = [
  { value: '+0%', label: '正常' },
  { value: '+15%', label: '稍快' },
  { value: '-25%', label: '稍慢' },
] as const

const router = useRouter()

const bubbles = ref<Bubble[]>([])
const history = ref<FreeChatMsg[]>([])
const inputText = ref('')
const sending = ref(false)
const recording = ref(false)
const errorMsg = ref<string | null>(null)
const currentAssistant = ref<Bubble | null>(null)
const playingBubble = ref<number | null>(null)
const chatBox = ref<HTMLElement | null>(null)
const rateIndex = ref((Number(localStorage.getItem('vv_rate_idx') ?? 0) % RATE_CYCLE.length + RATE_CYCLE.length) % RATE_CYCLE.length)
const rate = computed(() => RATE_CYCLE[rateIndex.value])

let replayAudio: HTMLAudioElement | null = null
let autoPlayToken = 0 // 回合自增：mounted 时递增，旧回合的播放回调失效

const recorder = new VoiceRecorder()
const abort = new AbortController()

onMounted(() => {
  void track('free_chat_open', {})
})

onUnmounted(() => {
  abort.abort()
  autoPlayToken += 1
  replayAudio?.pause()
  replayAudio = null
})

watch(
  () => bubbles.value.length,
  async () => {
    await nextTick()
    chatBox.value?.scrollTo({ top: chatBox.value.scrollHeight })
  },
)

function resetChat() {
  abort.abort()
  bubbles.value = []
  history.value = []
  errorMsg.value = null
  sending.value = false
  currentAssistant.value = null
  autoPlayToken += 1
  replayAudio?.pause()
  replayAudio = null
  playingBubble.value = null
  void track('free_chat_reset', {})
}

function goScene() {
  // 自由对话 → 口语 Hub（用户自选场景；边界不由自由对话直入具体场景，见 docs/14 §12.4）
  void track('free_chat_switch', { payload: { to: 'scene' } })
  router.push('/m/speaking')
}

function cycleRate() {
  rateIndex.value = (rateIndex.value + 1) % RATE_CYCLE.length
  localStorage.setItem('vv_rate_idx', String(rateIndex.value))
  void track('free_chat_rate', { payload: { rate: rate.value.value } })
}

function pushUser(text: string) {
  bubbles.value.push({ role: 'user', text })
  history.value.push({ role: 'user', content: text })
}

function streamTurn(form: FormData) {
  form.append('history', JSON.stringify(history.value.slice(-24)))
  sending.value = true
  errorMsg.value = null
  currentAssistant.value = null
  streamFreeChat(
    form,
    onSseEvent,
    (err) => {
      errorMsg.value = (err as Error).message
      sending.value = false
    },
    abort.signal,
  )
}

function sendText() {
  const text = inputText.value.trim()
  if (!text || sending.value || recording.value) return
  inputText.value = ''
  pushUser(text)
  const form = new FormData()
  form.append('text', text)
  void track('free_chat_turn', { payload: { audio: false } })
  streamTurn(form)
}

async function toggleMic() {
  if (sending.value) return
  if (recording.value) {
    if (recorder.state === 'recording') recorder.stop()
    else recorder.cancel()
    return
  }
  errorMsg.value = null
  recording.value = true
  try {
    await recorder.start(15_000)
  } catch (e) {
    recording.value = false
    errorMsg.value = micErrorMessage(e)
  }
}

recorder.onStateChange = (state) => {
  if (state !== 'recording') recording.value = false
}

recorder.onStop = (blob, _mime, durationMs) => {
  if (durationMs < MIN_RECORD_MS) {
    errorMsg.value = `录音太短（${(durationMs / 1000).toFixed(1)}s），请说满约 ${MIN_RECORD_MS / 1000} 秒后再点 ■ 停止`
    return
  }
  const form = new FormData()
  form.append('audio', blob, 'recording.webm')
  void track('free_chat_turn', { payload: { audio: true } })
  streamTurn(form)
}

function onSseEvent(e: SseStreamEvent) {
  switch (e.type) {
    case 'user_transcript':
      pushUser(e.text)
      break
    case 'text_delta':
      if (!currentAssistant.value) {
        bubbles.value.push({ role: 'assistant', text: '' })
        currentAssistant.value = bubbles.value[bubbles.value.length - 1]!
      }
      currentAssistant.value.text += e.text
      break
    case 'turn_end': {
      sending.value = false
      const reply = currentAssistant.value?.text ?? ''
      if (reply) {
        history.value.push({ role: 'assistant', content: reply })
        const idx = bubbles.value.length - 1
        const bubble = bubbles.value[idx]
        if (bubble && bubble.role === 'assistant') {
          bubble.speakable = true
          void playTts(reply, idx)
        }
      }
      currentAssistant.value = null
      break
    }
    case 'error':
      errorMsg.value = `自由对话提示：${e.code}`
      sending.value = false
      break
  }
}

/** 回合回复自动播报（微信式喇叭手动重听；自动播放被浏览器拒时静默降级为手动） */
async function playTts(text: string, index: number) {
  const token = autoPlayToken
  let done = false
  const finish = () => {
    if (!done) {
      done = true
      if (token === autoPlayToken && playingBubble.value === index) {
        playingBubble.value = null
        replayAudio = null
      }
    }
  }
  try {
    const blob = await tts(text, rate.value.value)
    if (!blob.size) {
      finish()
      return
    }
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.onended = () => {
      URL.revokeObjectURL(url)
      finish()
    }
    audio.addEventListener('loadedmetadata', () => {
      const ms = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration * 1000 + 400 : 8000
      setTimeout(finish, Math.min(ms, 15000))
    }, { once: true })
    setTimeout(finish, 15000)
    replayAudio?.pause()
    replayAudio = audio
    playingBubble.value = index
    await audio.play().catch(() => finish())
  } catch {
    finish()
  }
}

function replay(index: number, text: string) {
  if (!text) return
  if (playingBubble.value === index) {
    replayAudio?.pause()
    replayAudio = null
    playingBubble.value = null
    return
  }
  void playTts(text, index)
}
</script>

<template>
  <div class="u-phone">
    <div class="u-content u-fc-page">
      <button class="u-back u-back--float" type="button" title="返回" @click="router.back()">
        <MobileIcon name="back" />
      </button>

      <div ref="chatBox" class="u-fc-box">
        <div v-if="!bubbles.length" class="u-empty">
          <div class="u-empty__art"><MobileArt name="wave" :size="96" /></div>
          <div class="u-empty__title">自由对话</div>
          <div class="u-empty__sub">想聊什么就聊什么：点麦克风说，或直接打字。</div>
        </div>

        <template v-for="(m, i) in bubbles" :key="i">
          <div class="u-chat" :class="{ 'u-chat--user': m.role === 'user' }">
            <span v-if="m.role === 'assistant'" class="u-ava" style="background: var(--u-dark-teal)">
              <MobileIcon name="wave" :size="16" />
            </span>
            <div class="u-bubble" :class="m.role === 'user' ? 'u-bubble--user' : 'u-bubble--ai'">
              {{ m.text || '…' }}
              <button
                v-if="m.role === 'assistant' && m.speakable"
                class="u-replay"
                :class="{ 'is-playing': playingBubble === i }"
                type="button"
                :title="playingBubble === i ? '停止' : '重听'"
                :aria-label="playingBubble === i ? '停止播放' : '重听语音'"
                @click="replay(i, m.text)"
              >
                <template v-if="playingBubble === i">
                  <span class="u-eq" aria-hidden="true"><i /><i /><i /></span>
                </template>
                <MobileIcon v-else name="volume" :size="20" />
              </button>
            </div>
          </div>
        </template>

        <div v-if="errorMsg" class="u-error">{{ errorMsg }}</div>
      </div>

      <div class="u-fc-bar-wrap">
        <!-- Grok 式功能行（2026-09-05 组长拍板）：切场景 / 新对话 / 语速 -->
        <div class="u-tb" role="toolbar" aria-label="自由对话功能">
          <button class="u-tb-item" type="button" title="回到口语 Hub 选择场景" @click="goScene">
            <MobileIcon name="coffee" :size="22" />
            <span class="u-tb-item__label">场景对话</span>
          </button>
          <button
            class="u-tb-item"
            type="button"
            :disabled="!bubbles.length"
            title="清空当前对话，重新开始"
            @click="resetChat"
          >
            <MobileIcon name="refresh" :size="22" />
            <span class="u-tb-item__label">新对话</span>
          </button>
          <button
            class="u-tb-item"
            type="button"
            :title="`回复语速：${rate.label}（点击切换）`"
            @click="cycleRate"
          >
            <MobileIcon name="clock" :size="22" />
            <span class="u-tb-item__label">语速 · {{ rate.label }}</span>
          </button>
        </div>

        <div v-if="recording || sending" class="u-fc-state">
          {{ recording ? '聆听中… 点击 ■ 停止并发送' : 'AI 思考中…' }}
        </div>
        <div class="u-fc-bar">
          <input
            v-model="inputText"
            class="u-fc-input"
            type="text"
            placeholder="说英语或打字…"
            aria-label="聊天输入"
            :disabled="sending || recording"
            maxlength="2000"
            @keyup.enter="sendText"
          >
          <button
            class="u-fc-send"
            type="button"
            title="发送"
            aria-label="发送"
            :disabled="!inputText.trim() || sending || recording"
            @click="sendText"
          >
            <MobileIcon name="arrow" :size="20" />
          </button>
          <button
            class="u-fc-mic"
            :class="{ 'u-fc-mic--rec': recording }"
            type="button"
            :title="recording ? '停止录音' : '语音说话'"
            :aria-label="recording ? '停止录音' : '语音说话'"
            :disabled="sending"
            @click="toggleMic"
          >
            <MobileIcon :name="recording ? 'stop' : 'mic'" :size="20" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
