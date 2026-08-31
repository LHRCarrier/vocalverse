<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { asr, pingJava, readyz } from '@/api/client'
import { VoiceRecorder } from '@/audio/recorder'

const pythonStatus = ref('检查中…')
const javaStatus = ref('检查中…')
const recordState = ref('idle')
const recordInfo = ref('点击开始录音（M1 为 stub 转写）')

const recorder = new VoiceRecorder()
recorder.onStateChange = (s) => {
  recordState.value = s
}
recorder.onStop = async (blob, mime, durationMs) => {
  recordInfo.value = `录音完成: ${(blob.size / 1024).toFixed(1)} KB / ${(durationMs / 1000).toFixed(1)}s (${mime})，正在转写…`
  try {
    const r = await asr(blob)
    recordInfo.value = `转写: "${r.data.text}"（stub 演示）`
  } catch (e) {
    recordInfo.value = `转写失败: ${e instanceof Error ? e.message : String(e)}`
  }
}

async function toggleRecord() {
  if (recordState.value === 'recording') {
    recorder.stop()
    return
  }
  recordInfo.value = '录音中…（6 秒后自动停止）'
  try {
    await recorder.start()
  } catch (e) {
    recordInfo.value = `录音失败: ${e instanceof Error ? e.message : String(e)}`
  }
}

async function checkServices() {
  try {
    const r = await readyz()
    pythonStatus.value = `✓ ready (${r.data.app_env}, asr=${r.data.asr}, tts=${r.data.tts})`
  } catch {
    pythonStatus.value = '✗ Python 服务不可达（localhost:8000）'
  }
  try {
    const p = await pingJava()
    javaStatus.value = `✓ alive (${p.data.service})`
  } catch {
    javaStatus.value = '✗ Java 服务不可达（localhost:8080）'
  }
}

onMounted(checkServices)
</script>

<template>
  <div>
    <h1 class="mb-1 text-2xl font-bold">VocalVerse 声语界 · 框架骨架</h1>
    <p class="mb-6 text-sm text-[#667085]">
      M1 脚手架：三服务连通性 + 录音组件验证（docs/06 第 16 章）
    </p>

    <section class="mb-4 rounded-[12px] border border-[#E5E7EB] bg-white p-6">
      <h2 class="mb-3 font-semibold">服务连通</h2>
      <ul class="mb-4 space-y-1 text-sm">
        <li>Python（语音热路径）: {{ pythonStatus }}</li>
        <li>Java（管理端）: {{ javaStatus }}</li>
      </ul>
      <button
        class="rounded-full bg-brand px-4 py-1.5 text-sm text-white transition-colors hover:bg-brand-deep"
        @click="checkServices"
      >
        重新检查
      </button>
    </section>

    <section class="rounded-[12px] border border-[#E5E7EB] bg-white p-6">
      <h2 class="mb-3 font-semibold">录音组件（MediaRecorder → WebM/opus）</h2>
      <p class="mb-4 text-sm text-[#667085]">{{ recordInfo }}</p>
      <button
        class="rounded-full px-4 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60"
        :class="recordState === 'recording' ? 'bg-[#EF4444] text-white' : 'bg-accent text-[#101828]'"
        :disabled="recordState === 'recording'"
        @click="toggleRecord"
      >
        {{ recordState === 'recording' ? '停止' : '开始录音' }}
      </button>
    </section>
  </div>
</template>
