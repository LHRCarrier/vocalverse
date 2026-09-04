<script setup lang="ts">
/**
 * 移动端场景对话页（真形态 · 原型 app-speaking）：
 * 逻辑 = PracticeView 核心（docs/14 §3）——创建会话 → 开场 TTS → 录音 ≤15s → SSE 流
 * （字幕/音频队列/教练笔记/覆盖度）→ 收尾 → 报告；模板按原型「气泡 + 语言点 chip + 录音大按钮」。
 * audio 为时间轴权威、文本降级字幕（docs/06 §8）；救援：8s 无录音提示卡（docs/14 §2.3 L1）。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { track } from '@/api/events'
import { createSession, fetchScenarios, streamTurn, tts, type ScenarioItem } from '@/api/practice'
import type { SseStreamEvent } from '@/audio/sse-types'
import { VoiceRecorder, MIN_RECORD_MS, micErrorMessage } from '@/audio/recorder'
import { useTurnTimers } from '@/composables/useTurnTimers'
import '@/styles/mobile-uic.css'

interface Bubble {
  role: 'assistant' | 'user'
  text: string
  chips?: Array<{ phrase: string }>
}

const route = useRoute()
const router = useRouter()

const scenario = ref<ScenarioItem | null>(null)
const sessionId = ref<number | null>(null)
const currentTurn = ref(0)
const assignedTurns = ref(8)
const bubbles = ref<Bubble[]>([])
const recording = ref(false)
const phase = ref<'loading' | 'ready' | 'busy' | 'done'>('loading')
const lastScore = ref<{ pron?: number | null; flu?: number | null; gram?: number | null } | null>(null)
const scoreStatus = ref<'ok' | 'pending' | 'unavailable' | null>(null)
const corpusDone = ref<string[]>([])
const hitCount = computed(() => corpusDone.value.length)
const hintText = ref<string | null>(null)
const errorMsg = ref<string | null>(null)

const recorder = new VoiceRecorder()
const audioQueue: HTMLAudioElement[] = []
const abort = new AbortController()
const { setTimer, clearAll } = useTurnTimers()

const DIFFICULTY_LABEL: Record<number, string> = { 1: 'L1', 2: 'L2', 3: 'L3', 4: 'L4' }

onMounted(async () => {
  await boot()
})

onUnmounted(() => {
  abort.abort()
  audioQueue.forEach((a) => a.pause())
  clearAll()
})

async function boot() {
  try {
    const scenes = await fetchScenarios()
    const sceneId = Number(route.params.sceneId)
    scenario.value = scenes.find((s) => s.id === sceneId) ?? scenes[0] ?? null
    if (!scenario.value) {
      errorMsg.value = '没有可用场景，请先执行 seed'
      phase.value = 'done'
      return
    }
    const session = await createSession({
      kind: 'dialog',
      scenario_id: scenario.value.id,
      difficulty: scenario.value.difficulty,
    })
    sessionId.value = session.id
    assignedTurns.value = session.assigned_turns ?? 8
    await track('scene_start', { sceneId: scenario.value.id, payload: { session_id: session.id } })
    if (scenario.value.opening_line) {
      bubbles.value.push({ role: 'assistant', text: scenario.value.opening_line })
      playTts(scenario.value.opening_line)
    }
    phase.value = 'ready'
    armRescueTimer()
  } catch (e) {
    errorMsg.value = (e as Error).message
    phase.value = 'done'
  }
}

function armRescueTimer() {
  clearAll()
  if (phase.value !== 'ready') return
  setTimer(() => {
    if (!recording.value && phase.value === 'ready' && !hintText.value) {
      hintText.value = firstCorpusPhrase() ?? "Let's try: 'I would like a coffee, please.'"
    }
  }, 8000)
}

function firstCorpusPhrase(): string | null {
  const raw = scenario.value?.target_corpus ?? null
  if (!raw) return null
  const line = raw.split('\n').find((l) => l.includes('|'))
  return line ? line.split('|')[0]?.trim() ?? null : null
}

async function playTts(text: string) {
  try {
    const blob = await tts(text)
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.onended = () => URL.revokeObjectURL(url)
    await audio.play()
  } catch {
    /* 无声字幕继续 */
  }
}

function playChunk(url: string) {
  const audio = new Audio(url)
  audioQueue.push(audio)
  audio.onended = () => {
    audioQueue.shift()?.play().catch(() => undefined)
  }
  if (audioQueue.length === 1) audio.play().catch(() => undefined)
}

async function startRecording() {
  if (recording.value) {
    if (recorder.state === 'recording') recorder.stop()
    else recorder.cancel()
    return
  }
  if (phase.value !== 'ready') return
  hintText.value = null
  errorMsg.value = null
  recording.value = true
  try {
    void track('recording_start', { sceneId: scenario.value?.id })
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
  void track('recording_complete', { sceneId: scenario.value?.id }).catch(() => undefined)
  void sendTurn('normal', blob)
}

async function sendTurn(action: 'normal' | 'retry' | 'hint' | 'demo' | 'abandon', blob?: Blob) {
  if (!sessionId.value) return
  phase.value = 'busy'
  armRescueTimer()
  const form = new FormData()
  if (blob) form.append('audio', blob, 'recording.webm')
  form.append('action', action)
  form.append('expected_turn', String(currentTurn.value))
  bubbles.value.push({ role: 'assistant', text: '' })
  streamTurn(
    sessionId.value,
    form,
    onSseEvent,
    (err) => {
      errorMsg.value = (err as Error).message
      phase.value = 'ready'
    },
    abort.signal,
  )
}

function onSseEvent(e: SseStreamEvent) {
  const last = bubbles.value[bubbles.value.length - 1]
  switch (e.type) {
    case 'turn_start':
      if (e.reference_text) hintText.value = e.reference_text
      if (e.question) last.text = e.question
      break
    case 'text_delta':
      last.text += e.text
      break
    case 'audio_chunk':
      playChunk(e.url)
      break
    case 'meta_block':
      for (const hit of e.corpus_hits) {
        if (!corpusDone.value.includes(hit.phrase)) {
          corpusDone.value.push(hit.phrase)
          last.chips = last.chips ?? []
          last.chips.push({ phrase: hit.phrase })
        }
      }
      if (e.corpus_hits.length) void track('corpus_hit', { sceneId: scenario.value?.id, payload: { hits: e.corpus_hits } })
      break
    case 'score_delta':
      lastScore.value = { pron: e.pronunciation, flu: e.fluency, gram: e.grammar }
      scoreStatus.value = 'ok'
      void track('score_event', { sceneId: scenario.value?.id, payload: { pron: e.pronunciation, flu: e.fluency } })
      break
    case 'turn_end':
      scoreStatus.value = e.score_status === 'ok' ? scoreStatus.value : e.score_status
      currentTurn.value += 1
      phase.value = 'ready'
      armRescueTimer()
      break
    case 'session_end':
      phase.value = 'done'
      hintText.value = e.summary ?? '完成！'
      void track('practice_complete', { sceneId: scenario.value?.id, payload: { report_id: e.report_id } })
      setTimeout(() => {
        if (e.report_id) router.push(`/m/report?reportId=${e.report_id}`)
      }, 1200)
      break
    case 'error':
      errorMsg.value = `管线提示：${e.code}`
      break
  }
}
</script>

<template>
  <div class="u-phone">
    <div class="u-content">
      <!-- 头部：返回 + 场景 -->
      <header class="u-head" style="margin-bottom: 6px">
        <button class="u-back" type="button" title="返回" @click="router.back()">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M15 5l-7 7 7 7" />
          </svg>
        </button>
        <div style="flex: 1">
          <h1 style="font-size: 22px; font-weight: 700">{{ scenario?.title ?? '加载中…' }}</h1>
          <div style="font-size: 13px; color: var(--u-weak); margin-top: 3px">
            {{ DIFFICULTY_LABEL[scenario?.difficulty ?? 1] }} · 目标 ~{{ assignedTurns }} 轮 · 覆盖度 {{ hitCount }}
          </div>
        </div>
      </header>

      <!-- 回合指示 -->
      <div class="u-chip" style="margin: 18px 0 16px">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" />
        </svg>
        Round {{ currentTurn }} / {{ assignedTurns }}
      </div>

      <!-- 对话流 -->
      <div v-if="!bubbles.length && phase === 'loading'" class="u-empty">加载中…</div>
      <template v-for="(m, i) in bubbles" :key="i">
        <div class="u-chat" :class="{ user: m.role === 'user' }">
          <span v-if="m.role === 'assistant'" class="u-ava" style="background: #16303a">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M3 12h2M7 8v8M11 5v14M15 8v8M19 12h2" />
            </svg>
          </span>
          <div class="u-bubble" :class="m.role === 'user' ? 'user' : 'ai'">{{ m.text || '…' }}</div>
        </div>
        <div v-if="m.chips?.length" class="u-tips">
          <span v-for="(c, j) in m.chips" :key="j" class="u-chip">{{ '「' + c.phrase + '」已使用' }}</span>
        </div>
      </template>

      <!-- 救援提示卡（8s 无录音） -->
      <div v-if="hintText" class="u-hint">
        💡 {{ hintText }} —— 点击下方按钮，大声说出这句话。
      </div>

      <!-- 最近得分 -->
      <div v-if="lastScore && scoreStatus === 'ok'" class="u-tips">
        <span class="u-chip green">发音 {{ lastScore.pron ?? '—' }}</span>
        <span class="u-chip green">流利 {{ lastScore.flu ?? '—' }}</span>
        <span v-if="lastScore.gram != null" class="u-chip">语法 {{ lastScore.gram }}</span>
      </div>

      <div v-if="errorMsg" class="u-error">{{ errorMsg }}</div>
    </div>

    <!-- 录音大按钮 -->
    <div class="u-rec-label">{{ recording ? '录音中，点击 ■ 停止并提交' : '点击录音（≤15s）' }}</div>
    <button class="u-rec" :class="{ recording }" type="button" title="录音" @click="startRecording">
      <span v-if="recording" class="ring" />
      <svg v-if="!recording" viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
      </svg>
      <svg v-else viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <path d="M7 7h10v10H7z" />
      </svg>
    </button>
  </div>
</template>
