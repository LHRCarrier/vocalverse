<script setup lang="ts">
/**
 * 移动端 · 场景对话（口语陪练）——ui-concept-design skill 重制版
 * 逻辑 = 原 PracticeView 核心（docs/14 §3）：创建会话 → 开场 TTS → 录音 ≤15s → SSE 流
 * （字幕/音频队列/教练笔记/覆盖度）→ 收尾 → 报告（跳 /m/report?reportId=）。
 * 视觉（参考帧 ref-card-light-timeline + examples/app/speaking.html）：
 * AI 气泡 = track 灰底圆角 + 实色声波头像块；用户气泡 = 炭黑；语言点 = accent chip；
 * 得分 = 绿色 chip；救援 = 暖色卡；底部 = ink 实心圆形录音按钮（外圈波纹 + 忙碌旋转弧）。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { track } from '@/api/events'
import { createSession, fetchScenarios, streamTurn, tts, type ScenarioItem } from '@/api/practice'
import type { SseStreamEvent } from '@/audio/sse-types'
import { VoiceRecorder, MIN_RECORD_MS, micErrorMessage } from '@/audio/recorder'

import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import ScenePickerSheet from '@/components/mobile/ScenePickerSheet.vue'
import '@/styles/mobile-uic.css'

interface Bubble {
  role: 'assistant' | 'user'
  text: string
  chips?: Array<{ phrase: string }>
  /** 有可播语音（喇叭按钮出现条件；开场白进页即启用，回合语音播完后自动解锁，2026-09-08） */
  speakable?: boolean
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
const summaryText = ref<string | null>(null)
const errorMsg = ref<string | null>(null)
const reportId = ref<number | null>(null)
/* 聊天化：当前 AI 气泡（流式目标）+ 重听播放态 */
const currentAssistant = ref<Bubble | null>(null)
const playingBubble = ref<number | null>(null)
let replayAudio: HTMLAudioElement | null = null

const recorder = new VoiceRecorder()
const audioQueue: HTMLAudioElement[] = []
let abort = new AbortController()
const sheetOpen = ref(false)

onMounted(async () => {
  await boot()
})

onUnmounted(() => {
  abort.abort()
  audioQueue.forEach((a) => a.pause())
  replayAudio?.pause()
})

/* 功能行「场景选择」：页内切场景 = 重置状态后重新 boot（Hub 已删，2026-09-05） */
watch(
  () => route.params.sceneId,
  (v, old) => {
    if (old !== undefined && v !== old) void startScene()
  },
)

async function startScene() {
  abort.abort()
  abort = new AbortController()
  audioQueue.forEach((a) => a.pause())
  audioQueue.length = 0
  replayAudio?.pause()
  replayAudio = null
  if (recorder.state === 'recording') recorder.cancel()
  bubbles.value = []
  currentTurn.value = 0
  lastScore.value = null
  scoreStatus.value = null
  corpusDone.value = []
  summaryText.value = null
  errorMsg.value = null
  reportId.value = null
  currentAssistant.value = null
  playingBubble.value = null
  phase.value = 'loading'
  await boot()
}

function onScenePicked(sceneId: number) {
  if (sceneId === scenario.value?.id) return
  router.push(`/m/chat/${sceneId}`)
}

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
      // 开场白不自动播放（微信式：点喇叭才出声；2026-09-05 修「进页就自动响」）
      bubbles.value.push({ role: 'assistant', text: scenario.value.opening_line, speakable: true })
    }
    phase.value = 'ready'
  } catch (e) {
    errorMsg.value = (e as Error).message
    phase.value = 'done'
  }
}

/** 播放/重听 TTS；onDone = 播完回调（重听按钮出现条件）；index = 重听播放态记录 */
async function playTts(text: string, onDone?: () => void, index?: number) {
  let done = false
  const doneOnce = () => {
    if (!done) {
      done = true
      onDone?.()
    }
  }
  try {
    const blob = await tts(text)
    if (!blob.size) {
      // Fake 桩/未配音：空音频视为"已听过"（演示环境按钮可用）
      doneOnce()
      return
    }
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.onended = () => {
      URL.revokeObjectURL(url)
      if (index != null && playingBubble.value === index) {
        playingBubble.value = null
        replayAudio = null
      }
      doneOnce()
    }
    // 兜底：ended 事件在部分环境（headless/无音频设备）可能不触发 —— 按时长定时 + 15s 硬上限标记播完
    audio.addEventListener(
      'loadedmetadata',
      () => {
        const ms = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration * 1000 + 400 : 8000
        setTimeout(doneOnce, Math.min(ms, 15000))
      },
      { once: true },
    )
    setTimeout(doneOnce, 15000)
    if (index != null) {
      replayAudio?.pause()
      replayAudio = audio
      playingBubble.value = index
    }
    await audio.play().catch(() => {
      // autoplay 被拒/环境不支持：视为可重听入口已可用（用户点击时再播）
      if (index != null) {
        playingBubble.value = null
        replayAudio = null
      }
      doneOnce()
    })
  } catch {
    /* TTS 接口失败：不阻塞对话；重听按钮不出现 */
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
  void playTts(text, undefined, index)
}

function playChunk(url: string) {
  const audio = new Audio(url)
  audioQueue.push(audio)
  audio.onended = () => {
    audioQueue.shift()?.play().catch(() => undefined)
    // 全部音频块播完 = 本回合语音完整听了一遍 → 解锁喇叭按钮
    if (!audioQueue.length) {
      const lastAssistant = [...bubbles.value].reverse().find((b) => b.role === 'assistant')
      if (lastAssistant) lastAssistant.speakable = true
    }
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
  currentAssistant.value = null
  const form = new FormData()
  if (blob) form.append('audio', blob, 'recording.webm')
  form.append('action', action)
  form.append('expected_turn', String(currentTurn.value))
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
  switch (e.type) {
    case 'user_transcript':
      /* 用户语音 → 文字气泡（聊天效果，先于 AI 提问出现） */
      bubbles.value.push({ role: 'user', text: e.text })
      break
    case 'turn_start':
      bubbles.value.push({ role: 'assistant', text: e.question ?? '' })
      currentAssistant.value = bubbles.value[bubbles.value.length - 1]!
      break
    case 'text_delta':
      if (!currentAssistant.value) {
        bubbles.value.push({ role: 'assistant', text: '' })
        currentAssistant.value = bubbles.value[bubbles.value.length - 1]!
      }
      currentAssistant.value.text += e.text
      break
    case 'audio_chunk':
      playChunk(e.url)
      break
    case 'meta_block':
      for (const hit of e.corpus_hits) {
        if (!corpusDone.value.includes(hit.phrase)) {
          corpusDone.value.push(hit.phrase)
          const target = currentAssistant.value ?? bubbles.value[bubbles.value.length - 1]
          if (target) {
            target.chips = target.chips ?? []
            target.chips.push({ phrase: hit.phrase })
          }
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
      break
    case 'session_end':
      phase.value = 'done'
      summaryText.value = e.summary ?? '完成！'
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
    <div class="u-content u-content--dock" style="padding-top: 72px">
      <!-- 顶部只留返回按钮（文字全部去掉）；返回 = 口语模式入口不再依赖 history（2026-09-05：router.back() 会撞 /demo） -->
      <button class="u-back u-back--float" type="button" title="返回" @click="router.push('/m/home')">
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

      <!-- 会话中途错误（保留对话，红字提示） -->
      <div v-if="errorMsg && bubbles.length" class="u-error">{{ errorMsg }}</div>
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

      <!-- 会话结束：完成卡 + 查看报告 -->
      <section v-if="phase === 'done' && !errorMsg" class="u-done">
        <div class="u-done__art"><MobileArt name="done" :size="88" /></div>
        <div class="u-done__title">今日练习完成</div>
        <div class="u-done__sub">
          {{ summaryText ?? `共 ${bubbles.length} 轮对话 · 覆盖 ${hitCount} 个表达` }}
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
    <div class="u-tb u-tb--dock" role="toolbar" aria-label="口语功能">
      <button
        class="u-tb-item"
        type="button"
        title="切换到自由对话（AI 对聊，无固定题卡）"
        @click="router.push('/m/free-chat')"
      >
        <MobileIcon name="wave" :size="22" />
        <span class="u-tb-item__label">自由对话</span>
      </button>
      <button class="u-tb-item" type="button" title="切换预置场景" @click="sheetOpen = true">
        <MobileIcon name="chevron" :size="22" />
        <span class="u-tb-item__label">场景选择</span>
      </button>
    </div>

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

    <ScenePickerSheet :open="sheetOpen" @update:open="sheetOpen = $event" @select="onScenePicked" />
  </div>
</template>
