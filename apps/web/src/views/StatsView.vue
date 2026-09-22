<script setup lang="ts">
/**
 * 报表页（/stats · docs/53 P2 落地 · docs/13 §4 图表选型）。
 *
 * 三段：① 四指标看板（CTR/完成率/互动率/跳出率，口径 docs/06 §9.1 修订）；
 * ② 平台趋势（ECharts 折线：事件/会话/浏览）；③ 我的学习（五维雷达 + 概览 + 按类型）。
 * 导出：CSV（原始分子分母 + 趋势，可复算）与 PNG（趋势图，ECharts getDataURL）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { NButton, NCard, NRadioButton, NRadioGroup, NSpin } from 'naive-ui'

import type { EChartsOption } from 'echarts'

import { fetchStatsMe, fetchStatsOverview } from '@/api/stats'
import type { StatsMe, StatsOverview } from '@/api/stats'
import { useECharts } from '@/composables/useECharts'

const days = ref(30)
const overview = ref<StatsOverview | null>(null)
const me = ref<StatsMe | null>(null)
const loading = ref(false)
const error = ref('')

const trendEl = ref<HTMLElement | null>(null)
const radarEl = ref<HTMLElement | null>(null)

const METRIC_META = [
  { key: 'ctr', label: '点击率 CTR', hint: '曝光后 30min 内点击 / 曝光组' },
  { key: 'completion_rate', label: '完成率', hint: '完成单元 / 发起单元' },
  { key: 'interaction_rate', label: '互动率', hint: '玩家回合 / DM 回合 + 答辩作答' },
  { key: 'bounce_rate', label: '跳出率', hint: '1 − 参与率（>10s 或 关键事件 或 ≥2 浏览）' },
] as const

const metricCards = computed(() =>
  METRIC_META.map((m) => {
    const value = overview.value?.metrics[m.key]
    return {
      ...m,
      rate: value?.rate ?? null,
      ratio: value ? `${value.numerator} / ${value.denominator}` : '—',
    }
  }),
)

function pct(rate: number | null | undefined): string {
  return rate == null ? '—' : `${(rate * 100).toFixed(1)}%`
}

function trendOption(): EChartsOption {
  const rows = overview.value?.trend ?? []
  return {
    grid: { left: 44, right: 16, top: 32, bottom: 28 },
    tooltip: { trigger: 'axis' },
    legend: { data: ['事件', '浏览', '会话'], top: 0, right: 0, textStyle: { fontSize: 11 } },
    xAxis: { type: 'category', data: rows.map((r) => r.date.slice(5)), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
    series: [
      { name: '事件', type: 'line', smooth: true, data: rows.map((r) => r.events) },
      { name: '浏览', type: 'line', smooth: true, data: rows.map((r) => r.page_views) },
      { name: '会话', type: 'line', smooth: true, data: rows.map((r) => r.sessions) },
    ],
  }
}

function radarOption(): EChartsOption {
  const radar = me.value?.radar
  return {
    tooltip: {},
    radar: {
      indicator: (radar?.axes ?? []).map((name) => ({ name, max: 100 })),
      radius: '62%',
      axisName: { fontSize: 11 },
    },
    series: [
      {
        type: 'radar',
        data: [{ value: radar?.values ?? [], name: '我的五维' }],
        areaStyle: { opacity: 0.2 },
      },
    ],
  }
}

const trendChart = useECharts(trendEl, trendOption)
const radarChart = useECharts(radarEl, radarOption)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [o, m] = await Promise.all([fetchStatsOverview(days.value), fetchStatsMe(days.value)])
    overview.value = o
    me.value = m
    trendChart.setOption(trendOption())
    radarChart.setOption(radarOption())
  } catch (e) {
    error.value = (e as Error).message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(days, load)

function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

/** CSV 导出：分子/分母与趋势原始值（口径可复算，不只导比率） */
function exportCsv() {
  const o = overview.value
  if (!o) return
  const lines: string[] = ['section,key,numerator,denominator,rate']
  for (const key of ['ctr', 'completion_rate', 'interaction_rate', 'bounce_rate'] as const) {
    const v = o.metrics[key]
    lines.push(`metric,${key},${v.numerator},${v.denominator},${v.rate ?? ''}`)
  }
  lines.push('', 'date,events,page_views,sessions')
  for (const t of o.trend) lines.push(`${t.date},${t.events},${t.page_views},${t.sessions}`)
  lines.push('', 'date,attempts,avg_overall,sing')
  for (const t of me.value?.trend ?? []) {
    lines.push(`${t.date},${t.attempts},${t.avg_overall ?? ''},${t.sing}`)
  }
  download(`vocalverse-stats-${days.value}d.csv`, lines.join('\n'), 'text/csv;charset=utf-8')
}

function exportPng() {
  const dataUrl = trendChart.getDataURL()
  if (!dataUrl) return
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = `vocalverse-trend-${days.value}d.png`
  a.click()
}
</script>

<template>
  <div class="mx-auto max-w-[1080px] px-4 py-6">
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-bold">报表</h1>
        <p class="text-sm text-gray-500">
          四指标口径见 docs/06 §9.1（2026-09-21 修订：跳出率 = 1 − 参与率）
        </p>
      </div>
      <div class="flex items-center gap-2">
        <NRadioGroup v-model:value="days" size="small">
          <NRadioButton :value="7">7 天</NRadioButton>
          <NRadioButton :value="30">30 天</NRadioButton>
          <NRadioButton :value="90">90 天</NRadioButton>
        </NRadioGroup>
        <NButton size="small" :disabled="!overview" @click="exportCsv">导出 CSV</NButton>
        <NButton size="small" :disabled="!overview" @click="exportPng">导出 PNG</NButton>
        <NButton size="small" type="primary" :loading="loading" @click="load">刷新</NButton>
      </div>
    </div>

    <div v-if="error" class="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-600">{{ error }}</div>

    <NSpin :show="loading">
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <NCard v-for="c in metricCards" :key="c.key" size="small">
          <div class="text-xs text-gray-500">{{ c.label }}</div>
          <div class="mt-1 text-2xl font-bold tabular-nums">{{ pct(c.rate) }}</div>
          <div class="mt-1 text-xs text-gray-400">{{ c.ratio }}</div>
          <div class="mt-1 text-[11px] leading-4 text-gray-400">{{ c.hint }}</div>
        </NCard>
      </div>

      <NCard class="mt-4" size="small" title="平台趋势">
        <div ref="trendEl" style="height: 260px" />
      </NCard>

      <div class="mt-4 grid gap-3 lg:grid-cols-2">
        <NCard size="small" :title="`我的五维（近 ${days} 天）`">
          <div ref="radarEl" style="height: 260px" />
        </NCard>
        <NCard size="small" title="我的概览">
          <div class="grid grid-cols-2 gap-3 text-sm">
            <div>
              <div class="text-xs text-gray-500">练习会话</div>
              <div class="text-xl font-bold tabular-nums">{{ me?.summary.sessions ?? 0 }}</div>
            </div>
            <div>
              <div class="text-xs text-gray-500">练习分钟</div>
              <div class="text-xl font-bold tabular-nums">{{ me?.summary.practice_minutes ?? 0 }}</div>
            </div>
            <div>
              <div class="text-xs text-gray-500">口语录音</div>
              <div class="text-xl font-bold tabular-nums">{{ me?.summary.attempts ?? 0 }}</div>
            </div>
            <div>
              <div class="text-xs text-gray-500">跟唱录音</div>
              <div class="text-xl font-bold tabular-nums">{{ me?.summary.sing_attempts ?? 0 }}</div>
            </div>
            <div>
              <div class="text-xs text-gray-500">平均分</div>
              <div class="text-xl font-bold tabular-nums">{{ me?.summary.avg_overall ?? '—' }}</div>
            </div>
            <div>
              <div class="text-xs text-gray-500">最佳分</div>
              <div class="text-xl font-bold tabular-nums">{{ me?.summary.best_overall ?? '—' }}</div>
            </div>
          </div>
          <div v-if="me?.by_kind.length" class="mt-3 border-t border-gray-100 pt-2 text-xs text-gray-500">
            <span v-for="k in me.by_kind" :key="k.kind" class="mr-3">
              {{ k.kind }}：{{ k.count }} 次（均分 {{ k.avg_overall ?? '—' }}）
            </span>
          </div>
        </NCard>
      </div>

      <div class="mt-4 grid gap-3 lg:grid-cols-3">
        <NCard v-for="(rows, dim) in overview?.dimensions ?? {}" :key="dim" size="small" :title="`维度 · ${dim}`">
          <div v-if="!rows.length" class="text-xs text-gray-400">暂无数据</div>
          <div v-for="r in rows" :key="r.key" class="flex justify-between border-b border-gray-50 py-1 text-xs">
            <span class="truncate pr-2 text-gray-600">{{ r.key }}</span>
            <span class="tabular-nums text-gray-400">{{ r.events }}</span>
          </div>
        </NCard>
      </div>

      <div v-if="overview?.notes.length" class="mt-4 text-[11px] leading-5 text-gray-400">
        <div v-for="n in overview.notes" :key="n">· {{ n }}</div>
      </div>
    </NSpin>
  </div>
</template>
