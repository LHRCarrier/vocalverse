<script setup lang="ts">
/**
 * 学习指标（docs/53 P2）：四指标看板 + 平台趋势 + 维度 TopN（只读）。
 *
 * 数据源 = Python 控制台端点 `/api/v1/console/insight/overview`（口径 `app/insight/service.py`，
 * 与用户端 `/api/v1/stats/*` 同源）；权限码复用 `ops:metric:read`（见端点头注决策）。
 * 图表沿用控制台 Mono 发丝线（F2）与 `StatTile`，不引入 ECharts（本 SPA 的图表语言是自绘 SVG）。
 */
import { computed, onMounted, ref } from 'vue'

import { insightApi } from '@/api/insight'
import type { InsightOverview } from '@/api/types'
import ChartCard from '@/components/charts/ChartCard.vue'
import HairlineLine from '@/components/charts/HairlineLine.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatTile from '@/components/common/StatTile.vue'
import { fmtInt } from '@/utils/format'

const RANGES = [
  { days: 7, label: '近 7 天' },
  { days: 30, label: '近 30 天' },
  { days: 90, label: '近 90 天' },
]

const days = ref(30)
const data = ref<InsightOverview | null>(null)
const loading = ref(false)
const error = ref('')

const labels = computed(() => (data.value?.trend ?? []).map((p) => p.date.slice(5)))

const METRICS = [
  { key: 'ctr', label: '点击率 CTR', hint: '曝光后 30min 内点击 / 曝光组' },
  { key: 'completion_rate', label: '完成率', hint: '完成单元 / 发起单元' },
  { key: 'interaction_rate', label: '互动率', hint: '玩家回合 / DM 回合 + 答辩作答' },
  { key: 'bounce_rate', label: '跳出率', hint: '1 − 参与率（>10s 或 关键事件 或 ≥2 浏览）' },
] as const

const tiles = computed(() =>
  METRICS.map((m) => {
    const v = data.value?.metrics[m.key]
    return {
      key: m.key,
      label: m.label,
      hint: m.hint,
      value: v?.rate == null ? '—' : `${(v.rate * 100).toFixed(1)}%`,
      sub: v ? `${fmtInt(v.numerator)} / ${fmtInt(v.denominator)}` : '—',
    }
  }),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await insightApi.overview(days.value)
  } catch (e) {
    error.value = (e as Error).message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="学习指标"
      desc="四指标口径 = docs/06 §9.1（2026-09-21 修订：参与会话 >10s / 关键事件 / ≥2 浏览；跳出率 = 1 − 参与率）"
    >
      <template #actions>
        <div class="ins-ranges">
          <button
            v-for="r in RANGES"
            :key="r.days"
            type="button"
            class="ins-range"
            :class="{ 'ins-range--on': days === r.days }"
            @click="days = r.days; load()"
          >
            {{ r.label }}
          </button>
        </div>
        <button class="ins-range" type="button" :disabled="loading" @click="load">刷新</button>
      </template>
    </PageHeader>

    <p v-if="error" class="c-alert">{{ error }}</p>

    <div class="ins-tiles">
      <StatTile
        v-for="t in tiles"
        :key="t.key"
        :label="t.label"
        :value="t.value"
        :hint="`${t.sub} · ${t.hint}`"
        :loading="loading"
      />
    </div>

    <ChartCard
      title="埋点事件量与浏览会话的逐日走势"
      sub="事件 / 浏览 / 会话（近 {{ days }} 天）· 口径见 docs/06 §9.1"
      chart-no="F2"
      template-title="Thirty days of tracked events"
      source="events · /api/v1/console/insight/overview"
      :height="220"
      wide
    >
      <template #default="{ revealed }">
        <HairlineLine
          :labels="labels"
          :series="[
            { name: '事件', values: (data?.trend ?? []).map((p) => p.events), tone: 0 },
            { name: '浏览', values: (data?.trend ?? []).map((p) => p.page_views), tone: 2 },
            { name: '会话', values: (data?.trend ?? []).map((p) => p.sessions), tone: 4 },
          ]"
          unit=" 次"
          :format="(v) => fmtInt(v)"
          :revealed="revealed"
        />
      </template>
    </ChartCard>

    <div class="ins-grid">
      <section v-for="(rows, dim) in data?.dimensions ?? {}" :key="dim" class="c-card">
        <h2 class="c-card-title">维度 · {{ dim }}</h2>
        <p v-if="!rows.length" class="c-card-sub">暂无数据</p>
        <div v-for="r in rows" :key="r.key" class="ins-row">
          <span class="ins-row__key">{{ r.key }}</span>
          <span class="ins-row__n">{{ fmtInt(r.events) }}</span>
        </div>
      </section>
    </div>

    <div v-if="data" class="ins-foot">
      <span>统计窗口：{{ data.period.start.slice(0, 10) }} ~ {{ data.period.end.slice(0, 10) }}</span>
      <span>请求人：{{ data.requested_by ?? '—' }}</span>
      <span v-for="n in data.notes" :key="n">· {{ n }}</span>
    </div>
  </div>
</template>

<style scoped>
.ins-ranges {
  display: inline-flex;
  gap: 2px;
  margin-right: 6px;
}
.ins-range {
  border: 0;
  background: transparent;
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 12.5px;
  color: var(--c-text-2);
  cursor: pointer;
  transition: background var(--vv-t-micro) var(--vv-ease-out), color var(--vv-t-micro) var(--vv-ease-out);
}
.ins-range:hover {
  color: var(--c-text);
}
.ins-range--on {
  background: var(--c-surface-2, #f2f2ef);
  color: var(--c-text);
}
.ins-tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.ins-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
  margin-top: 16px;
}
.ins-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid var(--c-line, #eee);
  font-size: 12px;
}
.ins-row__key {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ins-row__n {
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
}
.ins-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
  font-size: 11px;
  opacity: 0.6;
}
</style>
