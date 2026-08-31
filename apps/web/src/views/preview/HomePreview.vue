<script setup lang="ts">
import { NButton, NTag } from 'naive-ui'

import { tokens } from '@/styles/tokens'

const tasks = [
  { title: '场景对话 · 咖啡馆', desc: '目标 5~8 轮 / 2~3 分钟', level: 'L3', color: tokens.colors.brand },
  { title: '复习 · 昨天错误词', desc: '6 个重难点词 + 音素提示', level: '复习', color: tokens.colors.brandLight },
  { title: '英文歌 · 试唱（M3）', desc: '跟唱评分 · 音准/节奏/发音', level: 'M3', color: tokens.colors.score },
]
</script>

<template>
  <div>
    <header class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="mb-1 text-2xl font-bold">下午好，LHR 👋</h1>
        <p class="text-sm text-[#667085]">今天完成 1 个场景即可保住 7 天连击</p>
      </div>
      <NTag round :bordered="false" :color="{ color: '#FACC15', textColor: '#101828' }">🔥 连击 12 天</NTag>
    </header>

    <h2 class="mb-3 font-semibold">今日任务</h2>
    <section class="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
      <article
        v-for="t in tasks"
        :key="t.title"
        class="rounded-[12px] border border-[#E5E7EB] bg-white p-5 transition-shadow hover:shadow-sm"
      >
        <div class="mb-3 flex items-center justify-between">
          <span class="rounded-full px-2.5 py-0.5 text-xs font-semibold text-white" :style="{ backgroundColor: t.color }">
            {{ t.level }}
          </span>
          <NTag size="small" :bordered="false">待完成</NTag>
        </div>
        <h3 class="mb-1 font-semibold">{{ t.title }}</h3>
        <p class="mb-4 text-sm text-[#667085]">{{ t.desc }}</p>
        <NButton size="small" round secondary type="primary">开始 →</NButton>
      </article>
    </section>

    <section class="rounded-[12px] border border-dashed border-[#E5E7EB] p-6 text-center">
      <p class="text-sm text-[#667085]">个性化推荐 + 水平预测（M3，docs/06 §9.5）——此处为推荐位预留</p>
    </section>
  </div>
</template>
