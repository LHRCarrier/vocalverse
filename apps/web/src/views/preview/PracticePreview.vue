<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NCard, NProgress, NTag } from 'naive-ui'

import { useP5Wave } from '@/composables/useP5Wave'

/**
 * ★ 场景对话页预览（M2 核心交互页）。
 * 全部为静态 mock；集成时替换为真实 SSE 对话流（docs/06 §8）。
 * TODO(M2)：messages ← 会话 API；score ← 评分接口；TTS 音频队列 + 字幕跟随。
 */
interface Bubble {
  role: 'assistant' | 'user'
  text: string
}

const messages = ref<Bubble[]>([
  {
    role: 'assistant',
    text: '你好！欢迎来到 Sunny Café ☕ 我是店员 Tom。今天想喝点什么？',
  },
  { role: 'user', text: 'I would like a coffee, please!' },
  { role: 'assistant', text: 'Great choice! With milk or black?' },
])
const waveRef = ref<HTMLElement | null>(null)
const recording = ref(false)

useP5Wave(waveRef, { height: 120 })

function toggleRecording() {
  recording.value = !recording.value
  // TODO(M2)：接入 VoiceRecorder + asr()（DemoView 已有实现可复用）
}
</script>

<template>
  <div class="mx-auto max-w-[880px]">
    <header class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold">场景 · 咖啡馆</h1>
        <p class="text-sm text-[#667085]">难度 L3 · 目标 5~8 轮 · Alex 的发音教练</p>
      </div>
      <NTag round :bordered="false" :color="{ color: '#ECFDF5', textColor: '#15803D' }">第 3 / 8 轮</NTag>
    </header>

    <!-- 对话流：音频为时间轴权威、文本为字幕（docs/06 §8） -->
    <section class="mb-4 space-y-3">
      <div
        v-for="(m, i) in messages"
        :key="i"
        class="flex"
        :class="m.role === 'user' ? 'justify-end' : 'justify-start'"
      >
        <div
          class="max-w-[70%] rounded-[12px] px-4 py-2.5 text-sm leading-relaxed"
          :class="
            m.role === 'user'
              ? 'rounded-br-[2px] bg-brand text-white'
              : 'rounded-bl-[2px] border border-[#E5E7EB] bg-white'
          "
        >
          {{ m.text }}
        </div>
      </div>
    </section>

    <!-- 录音区（核心交互：录音 → 波纹动效 → 转写 → 评分） -->
    <section class="mb-4 rounded-[12px] border border-[#E5E7EB] bg-white p-6 text-center">
      <div ref="waveRef" class="mx-auto h-[120px] w-full max-w-[420px] opacity-0 transition-opacity" :class="{ 'opacity-100': recording }" />
      <NButton
        class="mx-auto"
        circle
        size="large"
        :type="recording ? 'error' : 'primary'"
        @click="toggleRecording"
      >
        {{ recording ? '■' : '🎙' }}
      </NButton>
      <p class="mt-3 text-sm text-[#667085]">
        {{ recording ? '录音中…（30s 上限 / 自动停止）' : '点击说话 · ≤30s · WebM/opus' }}
      </p>
    </section>

    <!-- 评分卡：即时正反馈（体验增强候选 A-2） -->
    <NCard title="本句评分" size="small" class="mb-4">
      <div class="flex items-center gap-6">
        <div class="flex flex-col items-center">
          <NProgress type="circle" :percentage="88" color="#16A34A" />
          <span class="mt-1 text-xs text-[#667085]">综合</span>
        </div>
        <div class="flex-1 space-y-2">
          <div class="flex items-center gap-3">
            <span class="w-16 text-sm">发音</span>
            <NProgress class="flex-1" :percentage="90" color="#16A34A" :show-indicator="false" />
            <span class="w-8 text-right text-sm font-semibold">90</span>
          </div>
          <div class="flex items-center gap-3">
            <span class="w-16 text-sm">流利度</span>
            <NProgress class="flex-1" :percentage="86" color="#22C55E" :show-indicator="false" />
            <span class="w-8 text-right text-sm font-semibold">86</span>
          </div>
          <div class="flex items-center gap-3">
            <span class="w-16 text-sm">语法</span>
            <NProgress class="flex-1" :percentage="85" color="#FB923C" :show-indicator="false" />
            <span class="w-8 text-right text-sm font-semibold">85</span>
          </div>
        </div>
      </div>
      <p class="mt-3 rounded-[8px] bg-[#ECFDF5] px-3 py-2 text-xs text-[#15803D]">
        💡 would 弱读更自然；"a coffee" 重音落 a 更地道 —— 点下方高亮词听示范
      </p>
    </NCard>

    <!-- 建议 + 复练 -->
    <div class="flex justify-end gap-2">
      <NButton quaternary round>再来一遍</NButton>
      <NButton round type="primary">继续对话 →</NButton>
    </div>
  </div>
</template>
