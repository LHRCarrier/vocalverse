<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NButton } from 'naive-ui'

import { fetchRadar, fetchStatsOverview, fetchTrend } from '@/api/stats'
import type { MetricBoard, StatRadar, StatTrend } from '@/api/m3-types'
import MetricBoardView from '@/components/stats/MetricBoard.vue'
import RadarChart from '@/components/stats/RadarChart.vue'
import TrendChart from '@/components/stats/TrendChart.vue'

type Scope = 'oral' | 'sing'

const SCOPES: Array<{ key: Scope; label: string; desc: string }> = [
  { key: 'oral', label: '口语', desc: '发音 / 语法 / 流利度' },
  { key: 'sing', label: '唱歌', desc: '音准 / 节奏 / 发音' },
]

const scope = ref<Scope>('oral')
const metrics = ref<MetricBoard | null>(null)
const trend = ref<StatTrend | null>(null)
const radar = ref<StatRadar | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

async function loadCharts() {
  const [t, r] = await Promise.all([fetchTrend(scope.value), fetchRadar(scope.value)])
  trend.value = t
  radar.value = r
}

function switchScope(s: Scope) {
  if (s === scope.value) return
  scope.value = s
  void loadCharts().catch((e) => {
    error.value = (e as Error).message
  })
}

function exportSummary() {
  const data = {
    scope: scope.value,
    metrics: metrics.value,
    trend: trend.value,
    radar: radar.value,
    exportedAt: new Date().toISOString(),
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `vocalverse-${scope.value}-summary.json`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  try {
    const overview = await fetchStatsOverview()
    metrics.value = overview.metrics
    await loadCharts()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="mx-auto max-w-[1080px]">
    <header class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-2xl font-bold">学习报表</h1>
        <p class="mt-1 text-sm text-[#667085]">
          趋势 / 雷达 / 四指标看板（docs/06 §9.1）· 导出为 JSON 摘要（mock）
        </p>
      </div>
      <NButton round secondary @click="exportSummary">导出摘要</NButton>
    </header>

    <p v-if="error" class="mb-4 rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-xs text-[#B91C1C]">
      {{ error }}
    </p>

    <section v-if="loading" class="py-20 text-center text-sm text-[#667085]">加载报表中…</section>

    <div v-else-if="metrics && trend && radar" class="space-y-6">
      <MetricBoardView :metrics="metrics" />

      <div class="mb-3 flex gap-2">
        <NButton
          v-for="s in SCOPES"
          :key="s.key"
          round
          size="small"
          :type="scope === s.key ? 'primary' : 'default'"
          @click="switchScope(s.key)"
        >
          {{ s.label }} · {{ s.desc }}
        </NButton>
      </div>

      <section class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div class="rounded-[12px] border border-[#E5E7EB] bg-white p-4">
          <h2 class="mb-2 text-sm font-semibold text-[#667085]">成绩趋势</h2>
          <TrendChart :dates="trend.dates" :series="trend.series" />
        </div>
        <div class="rounded-[12px] border border-[#E5E7EB] bg-white p-4">
          <h2 class="mb-2 text-sm font-semibold text-[#667085]">多维雷达</h2>
          <RadarChart :dimensions="radar.dimensions" :values="radar.values" />
        </div>
      </section>
    </div>
  </div>
</template>