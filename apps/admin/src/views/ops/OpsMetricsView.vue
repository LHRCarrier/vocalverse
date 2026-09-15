<script setup lang="ts">
/**
 * 运维 · 性能指标（docs/50 §8.4 / §10.3）。
 *
 * 三个诚实性要求（缺一个这张页面就会骗人）：
 * 1. **口径写进副标题**——每个点的 `basis` 由后端给出（`sum(value_avg) over step` /
 *    `histogram_merge(...)` 等，query.py:294-307），界面照抄，不自己编一套说法；
 * 2. **step 在服务端二次聚合**——`(to-from)/step ≤ 5000` 点，超出返回 46007 + 建议 step，
 *    这里提前用 `suggestStep()` 对齐，避免用户一选 90 天就吃错误；
 * 3. **取平均再取分位数是错的**——分位指标由后端"合并直方图后重新插值"，
 *    窗口内没有直方图时后端**拒绝返回**（46007），点位 `value` 也可能是 `null`
 *    （该 step 无样本）——此时图上留空断线，绝不画成 0（那样会被读成"延迟为 0"）。
 *
 * 出参形状见 `services/python/app/console/api/routes/ops.py:252-261`：
 * `{from,to,step,series:{指标→点[]},rows_read,catalog:{指标→目录项}}`，
 * 不是"每个指标一个对象"的数组（v1 DTO 的 `MetricSeries[]` 就是臆造）。
 */
import { computed, onMounted, ref } from 'vue'

import { ApiError, opsApi } from '@/api'
import type { MetricCatalogItem, MetricPoint, MetricQueryResult } from '@/api'
import ChartCard from '@/components/charts/ChartCard.vue'
import HairlineLine from '@/components/charts/HairlineLine.vue'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { useAsync } from '@/composables/useAsync'
import { fmtCompact, fmtInt, fmtMs, lastDaysRange, suggestStep } from '@/utils/format'

const RANGES = [
  { label: '近 24 小时', days: 1 },
  { label: '近 7 天', days: 7 },
  { label: '近 14 天', days: 14 },
  { label: '近 30 天', days: 30 },
]

/** 单请求指标个数上限（后端 query.py:35 MAX_METRICS_PER_REQUEST=8） */
const MAX_METRICS = 8

interface ChartItem {
  name: string
  unit: string
  points: MetricPoint[]
}

const catalog = useAsync(() => opsApi.metricCatalog())
const result = ref<MetricQueryResult | null>(null)
const selected = ref<string[]>([])
const days = ref(7)
const loading = ref(false)
const error = ref<string | null>(null)
const errorCode = ref<number | null>(null)

const range = computed(() => lastDaysRange(days.value))
const step = computed(() => suggestStep(range.value.from, range.value.to))
const rangeLabel = computed(() => RANGES.find((r) => r.days === days.value)?.label ?? '')

const catalogMap = computed(
  () => new Map((catalog.state.value.data ?? []).map((m) => [m.name, m])),
)

/** 每个已选指标一张卡；点序列按后端返回的 series 直读（缺指标=空数组，不猜） */
const charts = computed<ChartItem[]>(() => {
  const res = result.value
  if (!res) return []
  return selected.value.map((name) => ({
    name,
    unit: res.catalog[name]?.unit ?? unitOf(name),
    points: res.series[name] ?? [],
  }))
})

function unitOf(name: string): string {
  return catalogMap.value.get(name)?.unit ?? ''
}

function description(name: string): string {
  return catalogMap.value.get(name)?.description ?? '口径未登记'
}

/** 后端逐点给出的聚合口径（query.py:300-307）——图表副标题必须照抄 */
function basisOf(item: ChartItem): string {
  return item.points.find((p) => p.basis !== '')?.basis ?? '口径未登记'
}

async function loadSeries(): Promise<void> {
  error.value = null
  errorCode.value = null
  if (!selected.value.length) {
    result.value = null
    return
  }
  loading.value = true
  try {
    result.value = await opsApi.metrics({
      metric: selected.value,
      from: range.value.from,
      to: range.value.to,
      step: step.value,
    })
  } catch (err) {
    const e = err as ApiError
    error.value = e.message
    errorCode.value = e.code
    result.value = null
  } finally {
    loading.value = false
  }
}

function toggle(metric: string): void {
  const on = selected.value.includes(metric)
  if (!on && selected.value.length >= MAX_METRICS) {
    error.value = `单请求最多 ${MAX_METRICS} 个指标（控制台看板与学习者热路径共池，后端硬限）`
    errorCode.value = 46007
    return
  }
  selected.value = on ? selected.value.filter((m) => m !== metric) : [...selected.value, metric]
  void loadSeries()
}

function setDays(next: number): void {
  days.value = next
  void loadSeries()
}

onMounted(async () => {
  await catalog.run()
  // 默认选三个"每天都会看"的指标，而不是空图让用户自己找
  selected.value = (catalog.state.value.data ?? []).slice(0, 3).map((m) => m.name)
  await loadSeries()
})

/** 结论文案：首末**有效点**的相对变化（null 点不参与，避免把"没采到"当成 0） */
function chartTitle(item: ChartItem): string {
  const vals = item.points.map((p) => p.value).filter((v): v is number => v !== null)
  if (vals.length < 2) return `${item.name} 暂无足够数据点`
  const first = vals[0]
  const last = vals[vals.length - 1]
  const delta = first === 0 ? 0 : (last - first) / first
  const dir = delta > 0.05 ? '在上升' : delta < -0.05 ? '在下降' : '基本持平'
  return `${item.name} ${dir}（首末有效点相对变化 ${(delta * 100).toFixed(1)}%）`
}

function formatY(metric: string): (v: number) => string {
  return unitOf(metric) === 'ms' ? (v) => fmtMs(v) : (v) => fmtCompact(v)
}

function isPercentile(m: MetricCatalogItem): boolean {
  return m.percentile_of !== null
}
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="性能指标"
      desc="按桶聚合的时序。指标口径在下方每个卡片的副标题中写明（口径文字由后端逐点给出）；无样本的桶留空断线，不画成 0。"
    >
      <template #actions>
        <div class="mt-ranges">
          <button
            v-for="r in RANGES"
            :key="r.days"
            type="button"
            class="mt-range"
            :class="{ 'mt-range--on': days === r.days }"
            @click="setDays(r.days)"
          >
            {{ r.label }}
          </button>
        </div>
      </template>
    </PageHeader>

    <section class="c-card mt-picker">
      <div class="c-card-head">
        <div>
          <h2 class="c-card-title">选择指标</h2>
          <p class="c-card-sub">
            服务端按 step = {{ step }}s 二次聚合 · 上限 5000 点/查询 · 单请求最多 {{ MAX_METRICS }} 个指标 ·
            指标保留 7 天<span v-if="result"> · 本次扫描 {{ fmtInt(result.rows_read) }} 行样本（预算 20000 行）</span>
          </p>
        </div>
        <span class="c-weak" style="font-size: 12px">已选 {{ selected.length }} / {{ MAX_METRICS }}</span>
      </div>

      <AsyncBlock
        :loading="catalog.state.value.loading"
        :error="catalog.state.value.error"
        :empty="!(catalog.state.value.data ?? []).length"
        empty-text="指标目录为空"
        empty-hint="APP_OPS_TELEMETRY_ENABLED 可能未开启"
        :min-height="80"
      >
        <div class="mt-chips">
          <button
            v-for="m in catalog.state.value.data ?? []"
            :key="m.name"
            type="button"
            class="mt-chip"
            :class="{ 'mt-chip--on': selected.includes(m.name) }"
            :title="`${m.description}${isPercentile(m) ? `（分位，真源 ${m.percentile_of}）` : ''}`"
            @click="toggle(m.name)"
          >
            {{ m.name }}
            <em v-if="m.unit" class="mt-chip-unit">{{ m.unit }}</em>
            <em v-if="isPercentile(m)" class="mt-chip-tag" title="分位指标：跨桶合并直方图重算">p</em>
          </button>
        </div>
      </AsyncBlock>
    </section>

    <AsyncBlock :loading="loading" :error="error" :error-code="errorCode" :empty="!charts.length" empty-text="没有数据点" :min-height="200">
      <div class="mt-grid">
        <ChartCard
          v-for="item in charts"
          :key="item.name"
          :title="chartTitle(item)"
          :sub="`${description(item.name)} · 聚合口径：${basisOf(item)} · ${rangeLabel} · step ${step}s · 无样本的桶留空`"
          chart-no="F2"
          template-title="Thirty days of sign-ups"
          :source="`ops_metric_samples · ${item.name}`"
          :height="190"
        >
          <template #default="{ revealed }">
            <HairlineLine
              :labels="item.points.map((p) => p.t.slice(5, 16).replace('T', ' '))"
              :series="[{ name: item.name, values: item.points.map((p) => p.value), tone: 0 }]"
              :unit="` ${item.unit}`"
              :format="formatY(item.name)"
              :revealed="revealed"
            />
          </template>
        </ChartCard>
      </div>
    </AsyncBlock>
  </div>
</template>

<style scoped>
.mt-ranges {
  display: flex;
  gap: 4px;
  padding: 3px;
  border-radius: 999px;
  background: var(--c-surface-sunken);
}
.mt-range {
  border: 0;
  background: transparent;
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 12.5px;
  color: var(--c-text-2);
  cursor: pointer;
  transition: background var(--vv-t-micro) var(--vv-ease-out), color var(--vv-t-micro) var(--vv-ease-out);
}
.mt-range:hover {
  color: var(--c-text);
}
.mt-range--on {
  background: var(--c-surface);
  color: var(--c-text);
  font-weight: 600;
  box-shadow: var(--c-shadow-1);
}
.mt-picker {
  margin-bottom: 14px;
}
.mt-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.mt-chip {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  border: 1px solid var(--c-border);
  background: transparent;
  border-radius: 999px;
  padding: 4px 11px;
  font-size: 12px;
  font-family: var(--vv-font-mono);
  color: var(--c-text-2);
  cursor: pointer;
  transition: all var(--vv-t-micro) var(--vv-ease-out);
}
.mt-chip:hover {
  border-color: var(--c-primary);
  color: var(--c-text);
}
.mt-chip--on {
  background: var(--c-text);
  border-color: var(--c-text);
  color: var(--c-surface);
}
.mt-chip-unit {
  font-style: normal;
  opacity: 0.6;
  font-size: 10.5px;
}
.mt-chip-tag {
  font-style: normal;
  font-size: 9.5px;
  border: 1px solid currentColor;
  border-radius: 3px;
  padding: 0 3px;
  opacity: 0.75;
}
.mt-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 14px;
}
</style>
