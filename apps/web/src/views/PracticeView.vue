<script setup lang="ts">
/**
 * ★ 场景对话主页面（docs/14 §3）：
 * 创建会话 → 开场(TTS) → 录音 ≤15s → POST /turns SSE 流 → 字幕/音频队列/徽章/教练笔记/覆盖度 → 收尾 → 报告。
 * 音频为时间轴权威、文本降级字幕（docs/06 §8）；救援：8s 无录音提示卡 + 用户主动（提示/示范/重说）。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NProgress, NTag } from 'naive-ui'

import { track } from '@/api/events'
import { createSession, fetchScenarios, streamTurn, tts, type ScenarioItem } from '@/api/practice'
import type { SseStreamEvent } from '@/audio/sse-types'
import { VoiceRecorder } from '@/audio/recorder'
import { useP5Wave } from '@/composables/useP5Wave'
import { useTurnTimers } from '@/composables/useTurnTimers'

interface Bubble {
  role: 'assistant' | 'user'
  text: string
  hits?: Array<{ phrase: string; state: 'ok' | 'fix' }>
  coach?: string | null
  grammar?: number | null
  scoreStatus?: 'ok' | 'pending' | 'unavailable'
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
const waveRef = ref<HTMLElement | null>(null)
const audioQueue: HTMLAudioElement[] = []
const abort = new AbortController()
const { setTimer, clearAll } = useTurnTimers()

useP5Wave(waveRef, { height: 110 })

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
    // 开场
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
  // 8s 无录音 → 提示卡（docs/14 §2.3 L1）
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
  if (phase.value !== 'ready') return
  hintText.value = null
  errorMsg.value = null
  try {
    recording.value = true
    await track('recording_start', { sceneId: scenario.value?.id })
    await recorder.start(15_000)
  } catch (e) {
    recording.value = false
    errorMsg.value = (e as Error).message
  }
}

recorder.onStateChange = (state) => {
  if (state !== 'recording') recording.value = false
}
recorder.onStop = (blob) => {
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
      last.coach = e.coach_note ?? null
      last.grammar = e.grammar?.score ?? null
      for (const hit of e.corpus_hits) {
        if (!corpusDone.value.includes(hit.phrase)) corpusDone.value.push(hit.phrase)
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
      last.scoreStatus = e.score_status
      currentTurn.value += 1
      phase.value = 'ready'
      armRescueTimer()
      break
    case 'session_end':
      phase.value = 'done'
      hintText.value = e.summary ?? '完成！'
      void track('practice_complete', { sceneId: scenario.value?.id, payload: { report_id: e.report_id } })
      setTimeout(() => {
        if (e.report_id) router.push(`/report/${e.report_id}`)
      }, 1200)
      break
    case 'error':
      errorMsg.value = `管线提示：${e.code}`
      break
  }
}

async function playDemo() {
  // 示范 = 只播放参考句音频，不产生回合（回合只在录音后发生——2026-09-01 修复无音频回合导致的 409）
  const phrase = hintText.value ?? firstCorpusPhrase() ?? ''
  if (phrase) playTts(phrase)
  await track('fun_action', { payload: { action: 'demo', trigger_by: 'user' } })
}
</script>

<template>
  <div class="mx-auto max-w-[880px]">
    <header class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold">场景 · {{ scenario?.title ?? '加载中…' }}</h1>
        <p class="text-sm text-[#667085]">
          难度 {{ DIFFICULTY_LABEL[scenario?.difficulty ?? 1] }} · 目标 ~{{ assignedTurns }} 轮 · 覆盖度
          <span class="font-semibold text-brandDeep">{{ hitCount }}</span>
        </p>
      </div>
      <NTag round :bordered="false" :color="{ color: '#ECFDF5', textColor: '#15803D' }">
        第 {{ currentTurn }} / {{ assignedTurns }} 轮
      </NTag>
    </header>

    <section class="mb-4 space-y-3">
      <div v-for="(m, i) in bubbles" :key="i" class="flex" :class="m.role === 'user' ? 'justify-end' : 'justify-start'">
        <div
          class="max-w-[70%] rounded-[12px] px-4 py-2.5 text-sm leading-relaxed"
          :class="
            m.role === 'user'
              ? 'rounded-br-[2px] bg-brand text-white'
              : 'rounded-bl-[2px] border border-[#E5E7EB] bg-white'
          "
        >
          {{ m.text || '…' }}
          <div v-if="m.coach" class="mt-2 rounded-[8px] bg-[#ECFDF5] px-3 py-1.5 text-xs text-brandDeep">
            🎓 {{ m.coach }}
          </div>
        </div>
      </div>
    </section>

    <!-- 救援提示卡（docs/14 §2.3 L1） -->
    <section
      v-if="hintText && phase === 'ready'"
      class="mb-4 flex items-center justify-between rounded-[12px] border border-[#FACC15] bg-[#FEFCE8] px-4 py-3"
    >
      <p class="text-sm"><span class="text-[#B45309]">💡 试试这样说：</span>{{ hintText }}</p>
      <div class="flex gap-2">
        <NButton size="small" round @click="playDemo">🔊 示范</NButton>
        <NButton size="small" round type="primary" @click="startRecording">🎙 试试说</NButton>
      </div>
    </section>

    <!-- 录音区 -->
    <section class="mb-4 rounded-[12px] border border-[#E5E7EB] bg-white p-6 text-center">
      <div
        ref="waveRef"
        class="mx-auto h-[110px] w-full max-w-[420px] opacity-0 transition-opacity"
        :class="{ 'opacity-100': recording }"
      />
      <NButton
        class="mx-auto"
        circle
        size="large"
        :type="recording ? 'error' : 'primary'"
        :disabled="phase !== 'ready'"
        @click="startRecording"
      >
        {{ recording ? '■' : '🎙' }}
      </NButton>
      <p class="mt-3 text-sm text-[#667085]">
        {{ recording ? '录音中…（≤15s 自动停止）' : '点击说话 · ≤15s · 听到 AI 回复后继续' }}
      </p>
    </section>

    <!-- 评分卡（回合内轻反馈：三色徽章 → docs/14 §3.6） -->
    <NCard v-if="lastScore" title="本句评分" size="small" class="mb-4">
      <div class="flex items-center gap-6">
        <div class="flex flex-col items-center">
          <NProgress
            type="circle"
            :percentage="Math.round((lastScore.pron ?? 0) * 0.4 + (lastScore.gram ?? 0) * 0.3 + (lastScore.flu ?? 0) * 0.3)"
            color="#16A34A"
          />
          <span class="mt-1 text-xs text-[#667085]">{{ scoreStatus === 'unavailable' ? '未评测' : '综合' }}</span>
        </div>
        <div class="flex-1 space-y-2">
          <div class="flex items-center gap-3">
            <span class="w-16 text-sm">发音</span>
            <NProgress class="flex-1" :percentage="lastScore.pron ?? 0" color="#16A34A" :show-indicator="false" />
            <span class="w-8 text-right text-sm font-semibold">{{ lastScore.pron ?? '—' }}</span>
          </div>
          <div class="flex items-center gap-3">
            <span class="w-16 text-sm">流利度</span>
            <NProgress class="flex-1" :percentage="lastScore.flu ?? 0" color="#22C55E" :show-indicator="false" />
            <span class="w-8 text-right text-sm font-semibold">{{ lastScore.flu ?? '—' }}</span>
          </div>
          <div class="flex items-center gap-3">
            <span class="w-16 text-sm">语法</span>
            <NProgress class="flex-1" :percentage="lastScore.gram ?? 0" color="#FB923C" :show-indicator="false" />
            <span class="w-8 text-right text-sm font-semibold">{{ lastScore.gram ?? '—' }}</span>
          </div>
        </div>
      </div>
    </NCard>

    <p v-if="errorMsg" class="mb-3 rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-xs text-[#B91C1C]">{{ errorMsg }}</p>

    <div class="flex items-center justify-end gap-2">
      <NButton quaternary round @click="sendTurn('abandon')">结束并查看报告</NButton>
      <NButton quaternary round @click="playDemo">🔊 听示范</NButton>
      <NButton round type="primary" :disabled="phase !== 'ready'" @click="startRecording">继续对话 ←</NButton>
    </div>
  </div>
</template>
