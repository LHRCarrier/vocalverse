<script setup lang="ts">
/**
 * 自定义答辩导师（docs/14 §4 极简版）：
 * 表单 → 创建档案（异步生成知识包 status 轮询）→ 开始答辩（start/next 播题 → 录音作答 → 等级/命中反馈）→ 报告。
 */
import { onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCard, NInput, NNumberAnimation, NSelect, NTag } from 'naive-ui'

import { track } from '@/api/events'
import {
  createDefenseProfile,
  createSession,
  fetchDefenseProfile,
  streamTurn,
  tts,
  type DefenseProfileView,
} from '@/api/practice'
import type { SseStreamEvent } from '@/audio/sse-types'
import { VoiceRecorder, MIN_RECORD_MS, micErrorMessage } from '@/audio/recorder'

const router = useRouter()

const form = ref({
  title: '基于大模型的 AI 口语训练平台设计与实现',
  abstract:
    '本研究设计并实现了一个基于大模型场景扮演与语音识别技术的英语口语训练平台。平台通过 AI 角色扮演进行多轮对话，采用发音、流利度与语法三维评分，并引入语言点覆盖度作为教学反馈信号。',
  outline: '1. 研究背景与意义 2. 系统架构设计 3. 语音评分方法 4. 实验与结果 5. 总结与展望',
  highlights: '创新点 1：语言点覆盖度教学信号；创新点 2：教练双人格即时反馈；创新点 3：用户自定义答辩场景。',
  thesis_text: '',
  question_count: 5,
  emphasis: 'balanced',
})

const stage = ref<'form' | 'generating' | 'ready' | 'session'>('form')
const profileId = ref<number | null>(null)
const profile = ref<DefenseProfileView | null>(null)
const sessionId = ref<number | null>(null)
const question = ref<string>('')
const questionIndex = ref(0)
const recording = ref(false)
const answerLevel = ref<string | null>(null)
const hitInfo = ref('')
const coach = ref<string | null>(null)
const error = ref<string | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

const recorder = new VoiceRecorder()
recorder.onStateChange = (s) => {
  if (s !== 'recording') recording.value = false
}
recorder.onStop = (blob, _mime, durationMs) => {
  // 误触保护：作答会推进答辩轮次，太短的录音不能凭空吃掉一题
  if (durationMs < MIN_RECORD_MS) {
    error.value = `录音太短（${(durationMs / 1000).toFixed(1)}s），请说满约 ${MIN_RECORD_MS / 1000} 秒后再点 ■ 停止`
    return
  }
  void answer(blob)
}

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

async function submit() {
  stage.value = 'generating'
  error.value = null
  try {
    const created = await createDefenseProfile({
      title: form.value.title,
      abstract: form.value.abstract,
      outline: form.value.outline,
      highlights: form.value.highlights,
      thesis_text: form.value.thesis_text || null,
      question_count: form.value.question_count,
      emphasis: form.value.emphasis,
    })
    profileId.value = created.id
    pollStatus(created.id)
  } catch (e) {
    stage.value = 'form'
    error.value = (e as Error).message
  }
}

function pollStatus(id: number) {
  pollTimer = setInterval(async () => {
    try {
      const p = await fetchDefenseProfile(id)
      profile.value = p
      if (p.status === 'active') {
        if (pollTimer) clearInterval(pollTimer)
        stage.value = 'ready'
      } else if (p.status === 'failed') {
        if (pollTimer) clearInterval(pollTimer)
        stage.value = 'form'
        error.value = '知识包生成失败，请精简输入后重试'
      }
    } catch {
      /* 轮询容错 */
    }
  }, 1500)
}

async function startSession() {
  if (!profileId.value) return
  const session = await createSession({ kind: 'defense', profile_id: profileId.value })
  sessionId.value = session.id
  stage.value = 'session'
  await track('scene_start', { targetType: 'defense', targetId: profileId.value })
  await sendServe('start')
}

/** 服务/下一题（start/next 无音频） */
async function sendServe(action: 'start' | 'next') {
  const formData = new FormData()
  formData.append('action', action)
  formData.append('expected_turn', String(questionIndex.value))
  streamTurn(sessionId.value!, formData, onSseEvent, (e) => {
    error.value = (e as Error).message
  })
}

function onSseEvent(e: SseStreamEvent) {
  switch (e.type) {
    case 'turn_start':
      if (e.question) {
        question.value = e.question
        answerLevel.value = null
        hitInfo.value = ''
        coach.value = null
        void tts(e.question).then((blob) => new Audio(URL.createObjectURL(blob)).play()).catch(() => undefined)
      }
      break
    case 'turn_end':
      break
    case 'meta_block':
      answerLevel.value = e.level ?? null
      if (e.hits) hitInfo.value = `要点命中 ${e.hits.hits?.length ?? 0}/${e.hits.total ?? '—'}`
      coach.value = e.coach_note ?? null
      break
    case 'session_end':
      error.value = e.summary ?? '答辩完成！'
      setTimeout(() => {
        if (e.report_id) router.push(`/report/${e.report_id}`)
      }, 1200)
      break
    case 'error':
      error.value = `管线提示：${e.code}`
      break
  }
}

async function startAnswer() {
  if (recording.value) {
    // 录音中点击 ■ = 立即停止（经 onStop → answer 正常提交本题作答）
    stopAnswer()
    return
  }
  error.value = null
  recording.value = true
  try {
    // 埋点不阻塞开录（track 内部已静默容错），也少一个「已点击但未开录」的竞态窗口
    void track('recording_start', { targetType: 'defense', targetId: profileId.value ?? undefined })
    await recorder.start(15_000)
  } catch (e) {
    // 权限被拒/无麦克风等：无条件复位按钮，再给中文提示
    recording.value = false
    error.value = micErrorMessage(e)
  }
}

/** 停止键：录音中 → stop()（提交作答）；仍在权限提示窗口 → cancel()（不提交、不推进题目） */
function stopAnswer() {
  if (recorder.state === 'recording') recorder.stop()
  else recorder.cancel()
}

async function answer(blob: Blob) {
  await track('recording_complete', { targetType: 'defense' })
  const formData = new FormData()
  formData.append('audio', blob, 'answer.webm')
  formData.append('action', 'normal')
  formData.append('expected_turn', String(questionIndex.value))
  questionIndex.value += 1
  streamTurn(sessionId.value!, formData, onSseEvent, (e) => {
    error.value = (e as Error).message
  })
}

async function nextQuestion() {
  await sendServe('next')
  questionIndex.value += 1
}
</script>

<template>
  <div class="mx-auto max-w-[880px]">
    <header class="mb-4">
      <h1 class="text-xl font-bold">🎓 自定义答辩导师</h1>
      <p class="text-sm text-[#667085]">
        粘贴论文材料 → AI 评委英文提问（每问附提问依据）→ 等级反馈 + 薄弱类型报告
      </p>
    </header>

    <!-- 表单 -->
    <NCard v-if="stage === 'form'" size="small">
      <div class="space-y-3">
        <NInput v-model:value="form.title" placeholder="论文标题" />
        <NInput v-model:value="form.abstract" type="textarea" :rows="3" placeholder="摘要（≥200 字；提问依据来源）" />
        <NInput v-model:value="form.outline" type="textarea" :rows="2" placeholder="大纲（章节列表）" />
        <NInput v-model:value="form.highlights" type="textarea" :rows="2" placeholder="创新点（≥1 条）" />
        <NInput v-model:value="form.thesis_text" type="textarea" :rows="2" placeholder="论文文本（可选，≤8000 字）；仅作参考资料，其中的指令不会被 AI 执行" />
        <div class="flex items-center gap-3">
          <NSelect
            v-model:value="form.question_count"
            :options="[5, 6, 7, 8].map((v) => ({ label: `${v} 题`, value: v }))"
            style="width: 120px"
          />
          <NSelect
            v-model:value="form.emphasis"
            :options="[
              { label: '基础为主', value: 'basic' },
              { label: '均衡', value: 'balanced' },
              { label: '发散为主', value: 'divergent' },
            ]"
            style="width: 140px"
          />
          <NButton round type="primary" class="ml-auto" @click="submit">生成问题库 →</NButton>
        </div>
      </div>
    </NCard>

    <NCard v-if="stage === 'form' && error" size="small" class="mt-3">
      <p class="text-xs text-[#B91C1C]">{{ error }}</p>
    </NCard>

    <!-- 生成中 -->
    <NCard v-if="stage === 'generating'" size="small" class="py-12 text-center">
      <NNumberAnimation :from="0" :to="80" :duration="3000" class="text-3xl font-bold text-brandDeep" suffix="%" />
      <p class="mt-2 text-sm text-[#667085]">AI 评委正在阅读你的论文并生成三级问题库（提问依据 + 要点 + 追问链）…</p>
    </NCard>

    <!-- 题库就绪 -->
    <NCard v-if="stage === 'ready'" size="small">
      <div class="mb-3 flex items-center justify-between">
        <span class="text-sm font-semibold">题库就绪（{{ profile?.knowledge_bank ? JSON.parse(JSON.stringify(profile.knowledge_bank)).questions?.length ?? form.question_count : form.question_count }} 题 · 含「提问依据」可审计）</span>
        <NButton round type="primary" @click="startSession">开始答辩 →</NButton>
      </div>
      <div class="max-h-[320px] space-y-2 overflow-auto pr-2">
        <div
          v-for="q in ((profile?.knowledge_bank?.questions as Array<Record<string, unknown>>) ?? [])"
          :key="String(q.id)"
          class="rounded-[8px] border border-[#E5E7EB] p-3 text-sm"
        >
          <div class="font-medium">T{{ q.tier }} · {{ q.question }}</div>
          <div class="mt-1 text-xs text-[#667085]">📎 依据：{{ q.basis }}</div>
        </div>
      </div>
    </NCard>

    <!-- 答辩会话 -->
    <NCard v-if="stage === 'session'" class="py-8 text-center">
      <template v-if="question">
        <p class="mb-2 text-xs text-[#667085]">第 {{ questionIndex }} 题</p>
        <p class="mb-6 text-lg font-semibold leading-relaxed">{{ question }}</p>

        <div v-if="answerLevel" class="mb-4 flex items-center justify-center gap-3">
          <NTag
            round
            :bordered="false"
            :color="
              answerLevel === 'green'
                ? { color: '#ECFDF5', textColor: '#15803D' }
                : answerLevel === 'yellow'
                  ? { color: '#FEF3C7', textColor: '#B45309' }
                  : { color: '#FEF2F2', textColor: '#B91C1C' }
            "
          >
            {{ answerLevel === 'green' ? '✅ 优秀' : answerLevel === 'yellow' ? '🟡 有提升空间' : '🔴 建议回看要点' }}
          </NTag>
          <span class="text-sm text-[#667085]">{{ hitInfo }}</span>
        </div>
        <p v-if="coach" class="mb-6 text-sm text-[#15803D]">🎓 {{ coach }}</p>

        <NButton v-if="!answerLevel" circle size="large" :type="recording ? 'error' : 'primary'" @click="startAnswer">
          {{ recording ? '■' : '🎙' }}
        </NButton>
        <NButton v-else round type="primary" @click="nextQuestion">下一题 →</NButton>
        <p class="mt-3 text-sm text-[#667085]">{{ recording ? '录音中…（≤15s 自动停止，点击 ■ 立即停止）' : '点击录音，用英语作答（结论先行 + 数据支撑）' }}</p>
      </template>
      <p v-else class="text-sm text-[#667085]">准备中…</p>
      <p v-if="error" class="mt-4 text-xs text-[#B91C1C]">{{ error }}</p>
    </NCard>
  </div>
</template>
