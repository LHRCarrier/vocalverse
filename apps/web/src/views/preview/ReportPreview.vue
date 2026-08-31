<script setup lang="ts">
import { NButton, NCard, NProgress } from 'naive-ui'

import { tokens } from '@/styles/tokens'

/** TODO(M3)：音素级错误定位数据来自评分接口（docs/06 §9.3）；音准曲线图 M3 用 D3/SVG 深定制 */
const sentence = {
  parts: [
    { text: 'I would ', ok: true },
    { text: 'like', ok: false }, // 错误词：/laɪk/ 末尾清塞音未释放
    { text: 'a coffee', ok: false },
    { text: ', please!', ok: true },
  ],
}

const dims = [
  { label: '发音', value: 90, color: tokens.colors.brand },
  { label: '语法', value: 85, color: tokens.colors.score },
  { label: '流利度', value: 86, color: tokens.colors.brandLight },
  { label: '完整度', value: 95, color: tokens.colors.info },
]
</script>

<template>
  <div class="mx-auto max-w-[880px]">
    <header class="mb-4">
      <h1 class="text-xl font-bold">评分报告 · 咖啡馆场景第 3 句</h1>
      <p class="text-sm text-[#667085]">2026-09-01 20:15 · L3 · 建议以句中单词级纠错为主</p>
    </header>

    <section class="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2">
      <NCard title="四维得分" size="small">
        <div class="space-y-3">
          <div v-for="d in dims" :key="d.label" class="flex items-center gap-3">
            <span class="w-14 text-sm">{{ d.label }}</span>
            <NProgress class="flex-1" :percentage="d.value" :color="d.color" :show-indicator="false" />
            <span class="w-8 text-right text-sm font-semibold">{{ d.value }}</span>
          </div>
        </div>
      </NCard>

      <NCard title="错误定位" size="small">
        <p class="mb-3 text-sm leading-relaxed">
          <template v-for="p in sentence.parts" :key="p.text">
            <span :class="p.ok ? '' : 'cursor-pointer rounded-[4px] bg-[#FEF3C7] px-1 font-semibold underline decoration-dashed decoration-[#F59E0B]'" :style="p.ok ? undefined : { color: '#B45309' }">
              {{ p.text }}
            </span>
          </template>
        </p>
        <p class="rounded-[8px] bg-[#ECFDF5] px-3 py-2 text-xs text-[#15803D]">
          👆 点黄色词：音素提示 + 正确示范（TTS）。"like" 辅音结尾要爆破清晰，重读元音 /aɪ/ 拖 0.2s 更自然。
        </p>
      </NCard>
    </section>

    <NCard title="改进建议" size="small" class="mb-4">
      <ul class="space-y-2 text-sm">
        <li>· <strong>would</strong> 在句中应弱读为 /wəd/，避免"单词蹦跳感"</li>
        <li>· <strong>a coffee</strong> 连读时辅音首尾相扣：/ə ˈkɒfi/</li>
        <li>· 语速 106 wpm，请保持（目标区间 90~110）</li>
      </ul>
    </NCard>

    <div class="flex justify-end gap-2">
      <NButton quaternary round>导出成绩卡（M3 社区）</NButton>
      <NButton round type="primary">再练一次 →</NButton>
    </div>
  </div>
</template>
