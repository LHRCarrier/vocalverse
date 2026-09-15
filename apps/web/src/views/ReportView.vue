<script setup lang="ts">
/** 评分报告最小集（docs/14 §5）：总分 + 覆盖度三栏 + 错误表（预览） + 建议 + 再练。 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NCard, NTag } from 'naive-ui'

import { fetchReport, type ReportPayload } from '@/api/practice'

const route = useRoute()
const router = useRouter()
const report = ref<ReportPayload | null>(null)
const error = ref<string | null>(null)

const overall = ref<{ pron: number; flu: number; gram: number } | null>(null)
/** 流利度辅助指标（docs/06 §9.3：语速 wpm + 停顿，来自 ASR 词级时间戳）。
 *  attempt 条目：{wpm, fluency_features:{pause_count,...}}，无数据时为 null/缺省。 */
const wpmAvg = ref<number | null>(null)
const pauseAvg = ref<number | null>(null)
/** ③ 语义子分（LLM 判定；进展示不进量化总分，docs/07 Q38） */
const semantic = ref<{ content: number | null; vocab: number | null; turns: number } | null>(null)

onMounted(async () => {
  try {
    report.value = await fetchReport(Number(route.params.reportId))
    const attempts = (report.value.metrics.attempts ?? []) as Array<Record<string, unknown>>
    const scored = attempts.filter((a) => a.pronunciation != null)
    if (scored.length) {
      const avg = (k: string) => scored.reduce((s, a) => s + Number(a[k] ?? 0), 0) / scored.length
      overall.value = { pron: Math.round(avg('pronunciation')), flu: Math.round(avg('fluency')), gram: Math.round(avg('grammar') ?? 0) }
      const wpmVals = scored
        .map((a) => Number(a.wpm ?? 0))
        .filter((v) => v > 0)
      if (wpmVals.length) {
        wpmAvg.value = Math.round(wpmVals.reduce((s, v) => s + v, 0) / wpmVals.length)
      }
      const pauseVals = scored
        .map((a) => {
          const f = a.fluency_features as Record<string, unknown> | undefined
          return f ? Number(f.pause_count ?? 0) : 0
        })
        .filter((v) => v > 0)
      if (pauseVals.length) {
        pauseAvg.value = Math.round((pauseVals.reduce((s, v) => s + v, 0) / pauseVals.length) * 10) / 10
      }
      // ③ 语义子分：metrics.semantic = {content:{score,turns}, vocab:{score,turns}}
      const sem = report.value.metrics.semantic as
        | { content?: { score?: number; turns?: number }; vocab?: { score?: number } }
        | null
      if (sem && (sem.content?.score != null || sem.vocab?.score != null)) {
        semantic.value = {
          content: sem.content?.score ?? null,
          vocab: sem.vocab?.score ?? null,
          turns: sem.content?.turns ?? 0,
        }
      }
    }
  } catch (e) {
    error.value = (e as Error).message
  }
})
</script>

<template>
  <div class="mx-auto max-w-[880px]">
    <header class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold">本次练习报告</h1>
        <p class="text-sm text-[#667085]">{{ report?.metrics.summary ?? '加载中…' }}</p>
      </div>
      <NButton round type="primary" @click="router.push('/practice')">再练一次 →</NButton>
    </header>

    <p v-if="error" class="mb-4 rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-xs text-[#B91C1C]">{{ error }}</p>

    <section v-if="overall" class="mb-4 grid grid-cols-3 gap-4">
      <NCard size="small">
        <div class="text-center">
          <div class="text-2xl font-bold text-brandDeep">{{ overall.pron }}</div>
          <div class="mt-1 text-xs text-[#667085]">发音</div>
        </div>
      </NCard>
      <NCard size="small">
        <div class="text-center">
          <div class="text-2xl font-bold text-[#B45309]">{{ overall.flu }}</div>
          <div class="mt-1 text-xs text-[#667085]">流利度</div>
          <div v-if="wpmAvg !== null" class="mt-1 text-[11px] text-[#667085]">
            语速 ≈ {{ wpmAvg }} 词/分<template v-if="pauseAvg !== null"> · 停顿 ≈ {{ pauseAvg }} 次/轮</template>
          </div>
        </div>
      </NCard>
      <NCard size="small">
        <div class="text-center">
          <div class="text-2xl font-bold text-[#0EA5E9]">{{ overall.gram }}</div>
          <div class="mt-1 text-xs text-[#667085]">语法</div>
        </div>
      </NCard>
    </section>

    <!-- ③ 语义子分（LLM 判定 · 展示口径，不进量化总分 · docs/07 Q38） -->
    <section v-if="semantic" class="mb-4 grid grid-cols-2 gap-4">
      <NCard size="small">
        <div class="text-center">
          <div class="text-2xl font-bold text-[#334EAC]">{{ semantic.content ?? '—' }}</div>
          <div class="mt-1 text-xs text-[#667085]">内容相关度（{{ semantic.turns }} 轮）</div>
        </div>
      </NCard>
      <NCard size="small">
        <div class="text-center">
          <div class="text-2xl font-bold text-[#7096D1]">{{ semantic.vocab ?? '—' }}</div>
          <div class="mt-1 text-xs text-[#667085]">词汇多样性 · 均分</div>
        </div>
      </NCard>
    </section>

    <!-- 覆盖度三栏（docs/14 §2.1：习得信号，不进总分） -->
    <NCard v-if="report?.metrics.coverage" title="语言点覆盖度（教学覆盖信号 · 不计入总分）" size="small" class="mb-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div class="rounded-[8px] bg-[#ECFDF5] p-3">
          <div class="mb-2 text-xs font-semibold text-brandDeep">✅ 自然达意（{{ report.metrics.coverage.covered.length }}）</div>
          <div class="space-y-1 text-sm">
            <div v-for="p in report.metrics.coverage.covered" :key="p">{{ p }}</div>
            <div v-if="!report.metrics.coverage.covered.length" class="text-xs text-[#667085]">本轮未出现</div>
          </div>
        </div>
        <div class="rounded-[8px] bg-[#FEF3C7] p-3">
          <div class="mb-2 text-xs font-semibold text-[#B45309]">⚠️ 需纠错（{{ report.metrics.coverage.needs_fix.length }}）</div>
          <div class="space-y-1 text-sm">
            <div v-for="p in report.metrics.coverage.needs_fix" :key="p">{{ p }}</div>
            <div v-if="!report.metrics.coverage.needs_fix.length" class="text-xs text-[#667085]">全部正确 👍</div>
          </div>
        </div>
        <div class="rounded-[8px] bg-[#F9FAFB] p-3">
          <div class="mb-2 text-xs font-semibold text-[#667085]">📌 待练（换个说法再试）</div>
          <div class="space-y-1 text-sm">
            <div v-for="p in report.metrics.coverage.to_practice" :key="p">{{ p }}</div>
            <div v-if="!report.metrics.coverage.to_practice.length" class="text-xs text-[#667085]">
              尝试用不同的目标表达再练一次
            </div>
          </div>
        </div>
      </div>
    </NCard>

    <!-- 建议 -->
    <NCard v-if="report?.metrics.suggestions?.length" title="改进建议" size="small" class="mb-4">
      <ul class="list-inside list-disc space-y-1.5 text-sm">
        <li v-for="(s, i) in report.metrics.suggestions" :key="i">{{ s }}</li>
      </ul>
    </NCard>

    <!-- 逐句回放为 P2 延后项（docs/14 §5）；此处展示轮次摘要 -->
    <NCard size="small">
      <div class="flex items-center justify-between">
        <span class="text-sm text-[#667085]">
          本会话 {{ (report?.metrics.attempts as unknown[])?.length ?? 0 }} 次有效录音 ·
          报告生成于 {{ report?.computed_at ? new Date(report.computed_at).toLocaleString() : '—' }}
        </span>
        <NTag round :bordered="false" :color="{ color: '#ECFDF5', textColor: '#15803D' }">
          {{ (report?.metrics.attempts as unknown[])?.length ?? 0 }} 轮评分
        </NTag>
      </div>
    </NCard>
  </div>
</template>
