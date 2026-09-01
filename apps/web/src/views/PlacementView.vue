<script setup lang="ts">
/**
 * 入学测试（docs/06 §9.2）：5 句固定朗读 + 1 轮 QA → 综合分 S → 水平档 L1~L4。
 * 每句录音 → ASR+ISE 评分（attempts.placement_item）；最后 finalize 出档位。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCard, NTag } from 'naive-ui'

import { request } from '@/api/client'
import { track } from '@/api/events'
import { VoiceRecorder } from '@/audio/recorder'

interface Q {
  id: number
  kind: 'read' | 'qa'
  prompt: string
}

interface R {
  q: Q
  attempt_id: number
  transcript?: string
  pron?: number | null
  flu?: number | null
  gram?: number | null
}

const router = useRouter()
const questions = ref<Q[]>([])
const index = ref(0)
const results = ref<R[]>([])
const recording = ref(false)
const uploading = ref(false)
const final = ref<{ level: string; total_score: number } | null>(null)
const error = ref<string | null>(null)

const recorder = new VoiceRecorder()
recorder.onStateChange = (s) => {
  if (s !== 'recording') recording.value = false
}
recorder.onStop = (blob) => {
  void upload(blob)
}

const done = computed(() => index.value >= questions.value.length)

onMounted(async () => {
  try {
    const resp = await request<Q[]>('/api/v1/placement/questions')
    questions.value = resp.data
  } catch (e) {
    error.value = (e as Error).message
  }
})

async function startRecord() {
  if (recording.value) return
  error.value = null
  recording.value = true
  await track('recording_start', { page: '/placement' })
  await recorder.start(15_000)
}

async function upload(blob: Blob) {
  uploading.value = true
  try {
    const q = questions.value[index.value]
    const form = new FormData()
    form.append('audio', blob, 'recording.webm')
    const resp = await request<{
      attempt_id: number
      transcript: string
      pron?: number | null
      flu?: number | null
      gram?: number | null
    }>(`/api/v1/placement/items/${q.id}/audio`, { method: 'POST', body: form })
    results.value.push({
      q,
      attempt_id: resp.data.attempt_id,
      transcript: resp.data.transcript,
      pron: resp.data.pron,
      flu: resp.data.flu,
      gram: resp.data.gram,
    })
    index.value += 1
    await track('recording_complete', { page: '/placement' })
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    uploading.value = false
  }
}

async function finish() {
  try {
    const resp = await request<{ level: string; total_score: number }>(
      '/api/v1/placement/finalize',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ attempts: results.value.map((r) => r.attempt_id) }),
      },
    )
    final.value = resp.data
    await track('practice_complete', { page: '/placement' })
    setTimeout(() => router.push('/practice'), 1500)
  } catch (e) {
    error.value = (e as Error).message
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
      <p class="text-sm text-[#667085]">朗读 5 句 + 回答 1 题 → 综合分 S = 0.4·发音 + 0.3·语法 + 0.3·流利 → 水平档 L1~L4</p>
    </header>

    <p v-if="error" class="mb-3 rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-xs text-[#B91C1C]">{{ error }}</p>

    <NCard v-if="!final && questions.length" class="mb-4">
      <template #header>
        <div class="flex items-center justify-between">
          <span>第 {{ index + 1 }} / {{ questions.length }} 题</span>
          <NTag round :bordered="false" :color="{ color: '#ECFDF5', textColor: '#15803D' }">
            {{ questions[index]?.kind === 'read' ? '📖 朗读' : '💬 回答' }}
          </NTag>
        </div>
      </template>
      <p class="mb-6 text-center text-lg font-semibold">{{ questions[index]?.prompt ?? '' }}</p>
      <div class="text-center">
        <NButton circle size="large" :type="recording ? 'error' : 'primary'" :disabled="uploading" @click="startRecord">
          {{ recording ? '■' : '🎙' }}
        </NButton>
        <p class="mt-3 text-sm text-[#667085]">{{ recording ? '录音中…（≤15s）' : '点击录音朗读本句' }}</p>
      </div>
    </NCard>

    <NCard v-if="final" class="py-10 text-center">
      <p class="text-sm text-[#667085]">你的综合分</p>
      <p class="my-2 text-5xl font-bold text-brandDeep">{{ Math.round(final.total_score) }}</p>
      <p class="mb-6 text-lg font-semibold">
        水平档：<NTag round :bordered="false" :color="{ color: '#ECFDF5', textColor: '#15803D' }">{{ final.level }}</NTag>
      </p>
      <NButton round type="primary" @click="router.push('/practice')">去练习 →</NButton>
    </NCard>

    <!-- 逐题结果列表 -->
    <NCard v-if="results.length" size="small" title="已完成">
      <div class="space-y-2">
        <div v-for="(r, i) in results" :key="i" class="flex items-center justify-between rounded-[8px] border border-[#E5E7EB] px-3 py-2 text-sm">
          <span class="max-w-[70%] truncate text-[#667085]">Q{{ i + 1 }} {{ r.q.prompt.slice(0, 30) }}…</span>
          <span class="flex items-center gap-3 text-xs">
            <span>发音 {{ format(r.pron) }}</span>
            <span>流利 {{ format(r.flu) }}</span>
            <span>语法 {{ format(r.gram) }}</span>
          </span>
        </div>
      </div>
    </NCard>

    <div v-if="done && !final" class="mt-4 text-center">
      <NButton round type="primary" size="large" @click="finish">完成测试，查看水平档 →</NButton>
    </div>
  </div>
</template>
