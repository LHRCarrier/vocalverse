<script setup lang="ts">
/**
 * 入学测试（docs/06 §9.2 · C1 两维 / C5 可跳过+2题 / C8 复测）。
 *
 * 双模式：
 * - initial：首次测试（可跳过 → provisional L2，见 POST /placement/skip）；
 * - retest：已有 completed 定档 → 复测（经 POST /placement/retest，40302/42902 gate 在后端）。
 * 每题：🔊 示范（TTS 读 prompt / QA reference_answer）+ 录音 + 重录一次 + 下一题；
 * 结束 finalize → 两维综合分 S → L1~L4。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCard, NTag } from 'naive-ui'

import { errorCopy } from '@/api/errorCopy'
import {
  finalizePlacement,
  fetchPlacementQuestions,
  fetchPlacementStatus,
  scorePlacementItem,
  skipPlacement,
  startRetest,
  type PlacementFinal,
  type PlacementQuestion,
  type PlacementStatus,
  type ScoreItemResult,
} from '@/api/placement'
import { tts } from '@/api/practice'
import { track } from '@/api/events'
import { MIN_RECORD_MS, micErrorMessage, VoiceRecorder } from '@/audio/recorder'

const router = useRouter()

const status = ref<PlacementStatus | null>(null)
const questions = ref<PlacementQuestion[]>([])
const phase = ref<'intro' | 'questions' | 'result'>('intro')
const index = ref(0)
const results = ref<(ScoreItemResult | null)[]>([])
const currentResult = ref<ScoreItemResult | null>(null)
const recording = ref(false)
const uploading = ref(false)
const final = ref<PlacementFinal | null>(null)
const error = ref<string | null>(null)
const demoUrl = ref<string | null>(null)
const testUrl = ref<string | null>(null)
const testMode = ref(false)

const recorder = new VoiceRecorder()
recorder.onStateChange = (s) => {
  if (s !== 'recording') recording.value = false
}
recorder.onStop = (blob, _mime, durationMs) => {
  if (testMode.value) {
    // 试音：回听，不消耗题目、不推进
    if (durationMs < MIN_RECORD_MS) {
      error.value = `试音太短（${(durationMs / 1000).toFixed(1)}s）：请说满约 ${Math.round(MIN_RECORD_MS / 1000)} 秒`
      return
    }
    if (testUrl.value) URL.revokeObjectURL(testUrl.value)
    testUrl.value = URL.createObjectURL(blob)
    testMode.value = false
    return
  }
  if (durationMs < MIN_RECORD_MS) {
    error.value = `录音太短（${(durationMs / 1000).toFixed(1)}s）：请说满约 ${Math.round(MIN_RECORD_MS / 1000)} 秒后再点 ■ 停止，本次不消耗题目`
    return
  }
  void upload(blob)
}

const current = computed(() => questions.value[index.value])
const isRetest = computed(() => Boolean(status.value?.has_completed))
const done = computed(() => index.value >= questions.value.length)

onMounted(async () => {
  try {
    status.value = await fetchPlacementStatus()
    if (!isRetest.value) {
      questions.value = await fetchPlacementQuestions()
    }
    if (status.value?.has_completed) {
      // 复测：先试音/说明，点「开始测试」时再走 retest 校验（40302/42902）
      phase.value = 'intro'
    }
  } catch (e) {
    error.value = errorCopy(e)
  }
})

onUnmounted(() => {
  // 卸载时释放 demo/试音 blob URL（避免内存/媒体资源泄漏）
  if (demoUrl.value) URL.revokeObjectURL(demoUrl.value)
  if (testUrl.value) URL.revokeObjectURL(testUrl.value)
  if (recorder.state === 'recording') recorder.stop()
})

async function beginTest() {
  error.value = null
  try {
    if (isRetest.value) {
      const r = await startRetest() // 40302 / 42902 gate 在此
      questions.value = r.questions
    } else if (!questions.value.length) {
      questions.value = await fetchPlacementQuestions()
    }
    results.value = new Array(questions.value.length).fill(null)
    currentResult.value = null
    index.value = 0
    phase.value = 'questions'
  } catch (e) {
    error.value = errorCopy(e)
  }
}

async function testMic() {
  testMode.value = true
  error.value = null
  try {
    await recorder.start(3_000)
  } catch (e) {
    testMode.value = false
    error.value = micErrorMessage(e)
  }
}

function toggleTestMic() {
  if (recording.value) stopRecord()
  else void testMic()
}

function playTest() {
  if (testUrl.value) void new Audio(testUrl.value).play()
}

async function playDemo() {
  const q = current.value
  if (!q) return
  const text = q.kind === 'qa' ? (q.reference_answer || q.prompt) : q.prompt
  try {
    const blob = await tts(text)
    if (demoUrl.value) URL.revokeObjectURL(demoUrl.value)
    demoUrl.value = URL.createObjectURL(blob)
    await new Audio(demoUrl.value).play()
  } catch (e) {
    error.value = errorCopy(e)
  }
}

async function startRecord() {
  if (recording.value) {
    stopRecord()
    return
  }
  error.value = null
  recording.value = true
  try {
    void track('recording_start', { page: '/placement' })
    await recorder.start(15_000)
  } catch (e) {
    recording.value = false
    error.value = micErrorMessage(e)
  }
}

function stopRecord() {
  if (recorder.state === 'recording') recorder.stop()
  else recorder.cancel()
}

async function upload(blob: Blob) {
  const q = current.value
  if (!q) return
  uploading.value = true
  try {
    const result = await scorePlacementItem(q.id, blob) // read: ASR+ISE；qa: 只 ASR(+语法诊断)
    results.value[index.value] = result
    currentResult.value = result
    void track('recording_complete', { page: '/placement' })
  } catch (e) {
    error.value = errorCopy(e)
  } finally {
    uploading.value = false
  }
}

function nextQuestion() {
  currentResult.value = null
  if (done.value) return
  index.value += 1
  error.value = null
}

async function finish() {
  error.value = null
  try {
    const attempts = results.value.filter((r): r is ScoreItemResult => r !== null).map((r) => r.attempt_id)
    final.value = await finalizePlacement(attempts)
    void track('practice_complete', { page: '/placement' })
    phase.value = 'result'
  } catch (e) {
    error.value = errorCopy(e)
  }
}

async function skip() {
  error.value = null
  try {
    const r = await skipPlacement() // provisional L2 → 通过 40303 门禁
    void track('fun_action', { page: '/placement', payload: { action: 'skip', target: 'placement' } })
    await router.push('/practice')
    void r
  } catch (e) {
    error.value = errorCopy(e)
  }
}

function format(v?: number | null) {
  return v == null ? '—' : Math.round(v)
}
</script>

<template>
  <div class="mx-auto max-w-[720px]">
    <header class="mb-4">
      <h1 class="text-xl font-bold">入学测试</h1>
      <p class="text-sm text-[#667085]">
        {{ isRetest ? '重新测试：刷新你的水平档' : '朗读 1 句 + 回答 1 题 → 综合分 S = 0.6·发音 + 0.4·流利度 → L1~L4' }}
      </p>
    </header>

    <p v-if="error" class="mb-3 rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-xs text-[#B91C1C]">{{ error }}</p>

    <!-- 试音 / 说明 -->
    <NCard v-if="phase === 'intro'" class="mb-4">
      <div class="text-center">
        <p class="mb-3 text-4xl">🎧</p>
        <p class="mb-1 text-base font-semibold">先试一下麦克风？</p>
        <p class="mb-5 text-sm text-[#667085]">
          按一次录音、说句话、再听一遍，确认设备没问题再开始。测试很短，放松说就好。
        </p>
        <div class="mb-5 flex items-center justify-center gap-3">
          <NButton round :type="recording ? 'error' : 'primary'" @click="toggleTestMic">
            {{ recording ? '■ 停止' : '🎙 试音' }}
          </NButton>
          <NButton v-if="testUrl" round secondary @click="playTest">🔊 回听试音</NButton>
        </div>
        <div class="flex flex-wrap items-center justify-center gap-3">
          <NButton round type="primary" size="large" @click="beginTest">开始测试 →</NButton>
          <NButton round secondary @click="skip">跳过测试，先练起来 →</NButton>
        </div>
        <p class="mt-4 text-xs text-[#667085]">跳过测试会先给你 L2 入门套，练完第一个场景再用真实水平回填。</p>
      </div>
    </NCard>

    <!-- 答题 -->
    <NCard v-if="phase === 'questions' && current" class="mb-4">
      <template #header>
        <div class="flex items-center justify-between">
          <span>第 {{ index + 1 }} / {{ questions.length }} 题</span>
          <NTag round :bordered="false" :color="{ color: '#ECFDF5', textColor: '#15803D' }">
            {{ current.kind === 'read' ? '📖 朗读' : '💬 回答' }}
          </NTag>
        </div>
      </template>
      <p class="mb-4 text-center text-lg font-semibold">{{ current.prompt }}</p>

      <p v-if="current.kind === 'qa'" class="mb-4 rounded-[8px] bg-[#F0F9FF] px-3 py-2 text-xs text-[#0369A1]">
        💡 参考方向：{{ current.reference_answer || '简要、连贯地介绍自己即可' }}
      </p>

      <div class="mb-4 flex items-center justify-center gap-3">
        <NButton round secondary :disabled="uploading" @click="playDemo">🔊 听示范</NButton>
        <NButton circle size="large" :type="recording ? 'error' : 'primary'" :disabled="uploading" @click="startRecord">
          {{ recording ? '■' : '🎙' }}
        </NButton>
      </div>
      <p class="text-center text-sm text-[#667085]">
        {{ recording ? '录音中…（≤15s 自动停止，点击 ■ 立即停止）' : '点击 🎙 录音作答' }}
      </p>

      <!-- 已录结果：评分 + 重录 / 下一题 -->
      <div v-if="currentResult" class="mt-5 rounded-[8px] border border-[#E5E7EB] p-4">
        <p class="mb-2 text-xs text-[#667085]">转写：{{ currentResult.transcript || '—' }}</p>
        <div class="mb-4 flex items-center justify-center gap-4 text-sm">
          <span>发音 <b>{{ format(currentResult.pron) }}</b></span>
          <span>流利 <b>{{ format(currentResult.flu) }}</b></span>
          <span>语法 <b>{{ format(currentResult.gram) }}</b></span>
        </div>
        <div class="flex justify-center gap-3">
          <NButton round secondary :disabled="uploading" @click="startRecord">
            🔁 重录一次
          </NButton>
          <NButton v-if="!done" round type="primary" @click="nextQuestion">下一题 →</NButton>
          <NButton v-else round type="primary" @click="finish">完成测试 →</NButton>
        </div>
      </div>
    </NCard>

    <!-- 结果 -->
    <NCard v-if="phase === 'result' && final" class="py-10 text-center">
      <p class="text-sm text-[#667085]">你的综合分</p>
      <p class="my-2 text-5xl font-bold text-brandDeep">{{ Math.round(final.total_score) }}</p>
      <p class="mb-6 text-lg font-semibold">
        水平档：<NTag round :bordered="false" :color="{ color: '#ECFDF5', textColor: '#15803D' }">{{ final.level }}</NTag>
      </p>
      <div class="flex flex-wrap justify-center gap-3">
        <NButton round type="primary" @click="router.push('/practice')">去练习 →</NButton>
        <NButton v-if="status?.has_completed" round secondary @click="router.push('/placement')">再测一次</NButton>
      </div>
    </NCard>

    <!-- 进度：已完成题目 -->
    <NCard v-if="phase === 'questions' && results.length" size="small" title="已完成">
      <div class="space-y-2">
        <div
          v-for="(r, i) in results"
          :key="i"
          class="flex items-center justify-between rounded-[8px] border border-[#E5E7EB] px-3 py-2 text-sm"
        >
          <span class="max-w-[70%] truncate text-[#667085]">Q{{ i + 1 }} {{ questions[i]?.prompt.slice(0, 30) }}…</span>
          <span class="flex items-center gap-3 text-xs">
            <template v-if="r">
              <span>发音 {{ format(r.pron) }}</span>
              <span>流利 {{ format(r.flu) }}</span>
              <span>语法 {{ format(r.gram) }}</span>
            </template>
            <span v-else class="text-[#98A2B3]">待录</span>
          </span>
        </div>
      </div>
    </NCard>
  </div>
</template>
