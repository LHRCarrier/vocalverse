<script setup lang="ts">
/**
 * 移动端 · 场景对话（口语陪练）——ui-concept-design skill 重制版
 * 逻辑 = 原 PracticeView 核心（docs/14 §3）：创建会话 → 开场 TTS → 录音 ≤15s → SSE 流
 * （字幕/音频队列/教练笔记/覆盖度）→ 收尾 → 报告（跳 /m/report?reportId=）。
 * 视觉（参考帧 ref-card-light-timeline + examples/app/speaking.html）：
 * AI 气泡 = track 灰底圆角 + 实色声波头像块；用户气泡 = 炭黑；语言点 = accent chip；
 * 得分 = 绿色 chip；救援 = 暖色卡；底部 = ink 实心圆形录音按钮（外圈波纹 + 忙碌旋转弧）。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { track } from '@/api/events'
import { createSession, fetchScenarios, streamTurn, tts, type ScenarioItem } from '@/api/practice'
import type { SseStreamEvent } from '@/audio/sse-types'
import { VoiceRecorder, MIN_RECORD_MS, micErrorMessage } from '@/audio/recorder'
import { useTurnTimers } from '@/composables/useTurnTimers'

import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
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
const reportId = ref<number | null>(null)

const recorder = new VoiceRecorder()
const audioQueue: HTMLAudioElement[] = []
const abort = new AbortController()
const { setTimer, clearAll } = useTurnTimers()

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
      errorMsg.value = '暂无可用场景，请先执行 seed 初始化演示数据。'
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

function bootAgain() {
  errorMsg.value = null
  phase.value = 'loading'
  void boot().catch(() => undefined)
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
      reportId.value = e.report_id ?? null
      void track('practice_complete', { sceneId: scenario.value?.id, payload: { report_id: e.report_id } })
      if (e.report_id) {
        setTimeout(() => {
          router.push(`/m/report?reportId=${e.report_id}`)
        }, 1600)
      }
      break
    case 'error':
      errorMsg.value = `管线提示：${e.code}`
      break
  }
}
</script>

<template>
  <div class="u-phone">
    <div class="u-content" style="padding-top: 72px">
      <!-- 顶部只留返回按钮（文字全部去掉） -->
      <button class="u-back u-back--float" type="button" title="返回" @click="router.back()">
        <MobileIcon name="back" />
      </button>

      <!-- 加载态：声波线稿锚点 -->
      <div v-if="!bubbles.length && phase === 'loading'" class="u-empty">
        <div class="u-empty__art"><MobileArt name="wave" :size="104" /></div>
        <div class="u-empty__title">正在进入场景…</div>
        <div class="u-empty__sub">数字人正在准备开场白，稍等片刻。</div>
      </div>

      <!-- 对话流：AI track 气泡 + 用户炭黑气泡 -->
      <template v-for="(m, i) in bubbles" :key="i">
        <div class="u-chat" :class="{ 'u-chat--user': m.role === 'user' }">
          <span v-if="m.role === 'assistant'" class="u-ava" style="background: #16303a">
            <MobileIcon name="wave" :size="16" />
          </span>
          <div class="u-bubble" :class="m.role === 'user' ? 'u-bubble--user' : 'u-bubble--ai'">
            {{ m.text || '…' }}
          </div>
        </div>
        <div v-if="m.chips?.length" class="u-tips">
          <span v-for="(c, j) in m.chips" :key="j" class="u-chip u-chip--accent">
            「{{ c.phrase }}」已使用
          </span>
        </div>
      </template>

      <!-- 最近得分（发音/流利绿色 chip；语法有值时显示） -->
      <div v-if="lastScore && scoreStatus === 'ok'" class="u-tips">
        <span class="u-chip u-chip--green">发音 {{ lastScore.pron ?? '—' }}</span>
        <span class="u-chip u-chip--green">流利 {{ lastScore.flu ?? '—' }}</span>
        <span v-if="lastScore.gram != null" class="u-chip u-chip--green">语法 {{ lastScore.gram }}</span>
      </div>

      <!-- 救援提示卡（8s 无录音） -->
      <div v-if="hintText && phase !== 'done'" class="u-hint">
        💡 {{ hintText }} —— 点击下方按钮，大声说出这句话。
      </div>

      <!-- 错误空态（未能进入场景：服务不可达 / 无数据） -->
      <section v-if="errorMsg && !bubbles.length && phase === 'done'" class="u-empty">
        <div class="u-empty__art"><MobileArt name="mic" :size="96" /></div>
        <div class="u-empty__title">无法进入场景</div>
        <div class="u-empty__sub">{{ errorMsg }}</div>
        <div class="u-done__actions" style="width: 100%; max-width: 280px">
          <button class="u-btn u-btn--primary u-btn--block" type="button" @click="bootAgain">
            重试
          </button>
          <RouterLink to="/m/home" class="u-btn u-btn--secondary u-btn--block">回到首页</RouterLink>
        </div>
      </section>

      <!-- 会话中途错误（保留对话，红字提示） -->
      <div v-else-if="errorMsg" class="u-error">{{ errorMsg }}</div>

      <!-- 会话结束：完成卡 + 查看报告 -->
      <section v-if="phase === 'done' && !errorMsg" class="u-done">
        <div class="u-done__art"><MobileArt name="done" :size="88" /></div>
        <div class="u-done__title">今日练习完成</div>
        <div class="u-done__sub">
          {{ hintText ?? `共 ${bubbles.length} 轮对话 · 覆盖 ${hitCount} 个表达` }}
        </div>
        <div class="u-done__actions">
          <button v-if="reportId" class="u-btn u-btn--primary u-btn--block" type="button" @click="router.push(`/m/report?reportId=${reportId}`)">
            <MobileIcon name="chart" :size="18" />
            查看评分报告
          </button>
          <RouterLink to="/m/home" class="u-btn u-btn--secondary u-btn--block">
            回到首页
          </RouterLink>
        </div>
      </section>
    </div>

    <!-- 录音大按钮（ink 圆形 + 波纹 / 忙碌旋转弧） -->
    <div v-if="phase !== 'done'" class="u-rec-label">
      {{ recording ? '录音中，点击 ■ 停止并提交' : phase === 'busy' ? '评分中，请稍候…' : '点击录音（≤15s）' }}
    </div>
    <button
      class="u-rec"
      :class="{ 'u-rec--recording': recording, 'u-rec--busy': phase === 'busy' }"
      :disabled="phase !== 'ready' && !recording"
      type="button"
      :title="recording ? '停止录音' : '开始录音'"
      @click="startRecording"
    >
      <span v-if="phase !== 'busy'" class="ring" />
      <span v-if="phase === 'busy'" class="arc" />
      <MobileIcon v-else-if="recording" name="stop" :size="26" />
      <MobileIcon v-else name="mic" :size="30" />
    </button>
  </div>
</template>
