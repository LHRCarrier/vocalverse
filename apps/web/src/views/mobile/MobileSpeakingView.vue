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
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
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
/**
 * 开始流程（2026-09-05 组长拍板：进页先选场景，选完 → 播放开场白 → 变回录音）：
 * choose = 未选场景（空态引导）；intro = 已就绪、开场白未播（底部按钮 = 播放图标）；
 * practice = 已点开始（底部按钮 = 录音图标，进入正常回合流）
 */
const stage = ref<'choose' | 'intro' | 'practice'>('choose')
const phase = ref<'loading' | 'ready' | 'busy' | 'done'>('loading')
const lastScore = ref<{ pron?: number | null; flu?: number | null; gram?: number | null } | null>(null)
const scoreStatus = ref<'ok' | 'pending' | 'unavailable' | null>(null)
const corpusDone = ref<string[]>([])
const hitCount = computed(() => corpusDone.value.length)
/** AI 状态线：loading（进场景）/busy（评分中）→ 流光；errorMsg → 纯红；其余纯黑（2026-09-05 组长拍板） */
const lineStatus = computed<'idle' | 'busy' | 'error'>(() => {
  if (errorMsg.value) return 'error'
  if (phase.value === 'loading' || phase.value === 'busy') return 'busy'
  return 'idle'
})
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
  // 无 sceneId（口语 Tab/中央 + 直达）→ 先让用户选场景；带 sceneId（场景选择/自由对话切换）→ 直接开工
  // 注意：params 缺省可能为 undefined 或 ''，两种都要判（2026-09-05 踩坑：'' 时被误放进场 → 未选场景先出题）
  const sid = route.params.sceneId
  if (sid !== undefined && sid !== '') {
    await startScene()
  } else {
    stage.value = 'choose'
  }
})

onUnmounted(() => {
  abort.abort()
  audioQueue.forEach((a) => a.pause())
  replayAudio?.pause()
})

/* 功能行「场景选择」/空态 CTA：页内切场景 = 重置状态后重新开工；:id → 无 id 回退到选场景态 */
watch(
  () => route.params.sceneId,
  (v, old) => {
    if (v === old) return
    if (v !== undefined && v !== '') {
      void startScene()
    } else if (old !== undefined && old !== '') {
      resetToChoose()
    }
  },
)

/** 清除全部会话状态（startScene / resetToChoose 共用） */
function resetChatState() {
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
}

async function startScene() {
  resetChatState()
  phase.value = 'loading'
  stage.value = 'practice' // 加载中先挂到练习态（隐藏「选场景」空态；boot 完成后按开场白落在 intro/practice）
  await boot()
}

/** :id → 无 id（如从 /m/chat/2 回到 /m/chat）：回退到「先选场景」 */
function resetToChoose() {
  resetChatState()
  phase.value = 'loading'
  stage.value = 'choose'
}

function onScenePicked(sceneId: number) {
  if (sceneId === scenario.value?.id) return
  router.push(`/m/chat/${sceneId}`)
}

async function boot() {
  try {
    const scenes = await fetchScenarios()
    if (!scenes.length) {
      errorMsg.value = '暂无可用场景，请先执行 seed 初始化演示数据。'
      phase.value = 'done'
      return
    }
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
      // 开场白不自动播放：进页不响；由底部「播放」按钮触发（2026-09-05 开始流程）
      bubbles.value.push({ role: 'assistant', text: scenario.value.opening_line, speakable: true })
      stage.value = 'intro'
    } else {
      stage.value = 'practice'
    }
    phase.value = 'ready'
  } catch {
    // 区分失败与无数据（2026-09-05：401/网络失败 ≠ 未 seed）
    errorMsg.value = '进入场景失败：请检查登录状态与网络后重试'
    phase.value = 'done'
  }
}

/** 开始流程第 2 步：点「播放」→ 播开场白 → 底部按钮变回录音；气泡喇叭态用既有 playTts 呈现 */
function playOpening() {
  if (stage.value !== 'intro') return
  stage.value = 'practice'
  const first = bubbles.value[0]
  if (first && first.text) {
    void playTts(first.text, undefined, 0)
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
  // 失败重试 = 重置后重开（含「先选场景」分支：带 sceneId 直接重开，无则回到 choose 态）
  if (route.params.sceneId !== undefined) {
    void startScene().catch(() => undefined)
  } else {
    stage.value = 'choose'
    errorMsg.value = null
    phase.value = 'loading'
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
    <!-- AI 状态线（静默纯黑 / 处理中彩色流光 / 出错纯红） -->
    <div
      class="v-line"
      :class="`v-line--${lineStatus}`"
      role="status"
      :aria-label="lineStatus === 'busy' ? 'AI 处理中' : lineStatus === 'error' ? '出错了' : '空闲'"
    />
    <!-- 统一顶栏（返回 + 全局头像 / 口语 / 场景选择） -->
    <MobileTopBar title="口语" back @back="router.push('/m/home')">
      <template #actions>
        <button class="u-topbar__act" type="button" title="选择场景" aria-label="选择场景" @click="sheetOpen = true">
          <MobileIcon name="coffee" :size="18" />
        </button>
      </template>
    </MobileTopBar>
    <div class="u-content u-content--dock">
      <!-- 开始流程第 1 步：先选场景（只留图 + 按钮；按钮仅此一个，底部功能行的重复入口在 choose 态隐藏） -->
      <section v-if="stage === 'choose'" class="u-empty u-empty--center">
        <div class="u-empty__art"><MobileArt name="mic" :size="96" /></div>
        <div class="u-done__actions" style="width: 100%; max-width: 280px">
          <button class="u-btn u-btn--primary u-btn--block" type="button" @click="sheetOpen = true">
            选择场景
          </button>
        </div>
      </section>

      <!-- 加载态：状态线已表达”处理中“，这里只留居中线稿锚点（无文案；2026-09-05） -->
      <div v-else-if="!bubbles.length && phase === 'loading'" class="u-empty u-empty--center" role="status" aria-label="正在进入场景">
        <div class="u-empty__art"><MobileArt name="wave" :size="96" /></div>
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

    <!-- 底部 dock（2026-09-05：标签已删；开始流程 = 播放图标 → 点击开始 → 变回录音） -->
    <div class="u-chat-dock">
      <button
        v-if="stage !== 'choose'"
        class="u-rec"
        :class="{ 'u-rec--recording': recording, 'u-rec--busy': phase === 'busy' }"
        :disabled="phase !== 'ready' && !recording"
        type="button"
        :title="stage === 'intro' ? '开始练习（播放开场白）' : recording ? '停止录音' : '开始录音'"
        :aria-label="stage === 'intro' ? '开始练习' : recording ? '停止录音' : '开始录音'"
        @click="stage === 'intro' ? playOpening() : startRecording()"
      >
        <span v-if="phase !== 'busy'" class="ring" />
        <span v-if="phase === 'busy'" class="arc" />
        <template v-else-if="stage === 'intro'">
          <MobileIcon name="play" :size="30" />
        </template>
        <MobileIcon v-else-if="recording" name="stop" :size="26" />
        <MobileIcon v-else name="mic" :size="30" />
      </button>

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
        <button
          v-if="stage !== 'choose'"
          class="u-tb-item"
          type="button"
          title="切换预置场景"
          @click="sheetOpen = true"
        >
          <MobileIcon name="chevron" :size="22" />
          <span class="u-tb-item__label">场景选择</span>
        </button>
      </div>
    </div>

    <ScenePickerSheet :open="sheetOpen" @update:open="sheetOpen = $event" @select="onScenePicked" />
  </div>
</template>
