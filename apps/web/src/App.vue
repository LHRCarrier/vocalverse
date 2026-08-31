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
  <main class="shell">
    <h1>VocalVerse 声语界 · 框架骨架</h1>
    <p class="sub">M1 脚手架：三服务连通性 + 录音组件验证（docs/06 第 16 章）</p>

    <section class="card">
      <h2>服务连通</h2>
      <ul>
        <li>Python（语音热路径）: {{ pythonStatus }}</li>
        <li>Java（管理端）: {{ javaStatus }}</li>
      </ul>
      <button @click="checkServices">重新检查</button>
    </section>

    <section class="card">
      <h2>录音组件（MediaRecorder → WebM/opus）</h2>
      <p>{{ recordInfo }}</p>
      <button :disabled="recordState === 'recording'" @click="toggleRecord">
        {{ recordState === 'recording' ? '停止' : '开始录音' }}
      </button>
    </section>
  </main>
</template>

<style scoped>
.shell {
  max-width: 720px;
  margin: 3rem auto;
  font-family: system-ui, sans-serif;
}
.sub {
  color: #666;
}
.card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin: 1rem 0;
}
button {
  padding: 0.4rem 1rem;
  cursor: pointer;
}
</style>
