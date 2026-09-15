<script setup lang="ts">
/**
 * 工作台 · 运维面板（docs/50 §11.3「工作台按角色分流」）。
 *
 * 运维登录后第一眼要看的是：**服务活着吗 / 有没有未处理预警 / 延迟在恶化吗**。
 * 因此三块内容按这个顺序排，而不是先摆一堆漂亮图表。
 *
 * ⚠️ 字段按 ops.py:87-112 / 562-573 直读：`dependencies.items`（不是 probes）、
 * `self_monitoring.*`（不是 selfMonitor）、`duration_ms_p95`（不是 durationP95）。
 * trace 统计**没有按日趋势**（后端只返回窗口汇总），所以这里不再画趋势图——
 * 画一张读不到数据的空图比不画更糟。
 */
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'

import { opsApi } from '@/api'
import type { DependencyProbe } from '@/api'
import StatTile from '@/components/common/StatTile.vue'
import { useAsync, useRealtimeRefresh } from '@/composables/useAsync'
import { fmtCompact, fmtDuration, fmtMs, fmtPercent, lastDaysRange } from '@/utils/format'

const WINDOW_DAYS = 14
const range = lastDaysRange(WINDOW_DAYS)

const overview = useAsync(() => opsApi.overview())
const stats = useAsync(() => opsApi.traceStats(range))

onMounted(() => {
  void overview.run()
  void stats.run()
})

// 运维页是"看现状"的页面：15s 轮询即可，不上 SSE（docs/50 §15.1 已登记不做实时推送）
useRealtimeRefresh(() => {
  void overview.run()
  void stats.run()
}, 15_000)

const deps = computed(() => overview.state.value.data?.dependencies ?? null)
const probes = computed(() => deps.value?.items ?? [])
const unhealthy = computed(() => probes.value.filter((p) => !p.ok).length)
const self = computed(() => overview.state.value.data?.self_monitoring)
const trace = computed(() => stats.state.value.data)

const STATUS_LABEL: Record<DependencyProbe['status'], string> = {
  ready: '正常',
  degraded: '降级',
  not_ready: '不可用',
}
const depText = computed(() => (deps.value ? STATUS_LABEL[deps.value.status] : '—'))
const depTone = computed<'ok' | 'warn' | 'danger' | undefined>(() => {
  if (!deps.value) return undefined
  if (deps.value.status === 'ready') return 'ok'
  return deps.value.status === 'degraded' ? 'warn' : 'danger'
})
</script>

<template>
  <div class="dp-grid">
    <div class="c-stat-row dp-stats">
      <StatTile
        label="依赖健康"
        :value="depText"
        :tone="depTone"
        :hint="`共探测 ${probes.length} 项依赖，${unhealthy} 项异常`"
        :loading="overview.state.value.loading"
      />
      <StatTile
        label="运行时长"
        :value="overview.state.value.data ? fmtDuration(overview.state.value.data.uptime_s) : '—'"
        :hint="overview.state.value.data ? `版本 ${overview.state.value.data.version} · ${overview.state.value.data.app_env}` : ''"
        :loading="overview.state.value.loading"
      />
      <StatTile
        label="LLM 错误率"
        :value="trace ? fmtPercent(trace.error_rate, 2) : '—'"
        :tone="trace && trace.error_rate > 0.1 ? 'danger' : undefined"
        :hint="trace ? `近 ${WINDOW_DAYS} 天 · 失败 ${trace.error_count} / 总 ${trace.trace_count} 条` : `近 ${WINDOW_DAYS} 天`"
        :loading="stats.state.value.loading"
      />
      <StatTile
        label="LLM 耗时 p95"
        :value="trace ? fmtMs(trace.duration_ms_p95) : '—'"
        :tone="trace && trace.duration_ms_p95 !== null && trace.duration_ms_p95 > 8000 ? 'warn' : undefined"
        :hint="trace?.duration_ms_p95_basis ?? '窗口内无直方图样本时后端拒绝给数'"
        :loading="stats.state.value.loading"
      />
    </div>

    <section class="c-card">
      <div class="c-card-head">
        <div>
          <h2 class="c-card-title">依赖探测</h2>
          <p class="c-card-sub">与容器健康检查同源（同一个 probe 函数），因此这里显示什么、健康检查就报什么</p>
        </div>
        <RouterLink to="/ops" class="dp-link">查看详情</RouterLink>
      </div>
      <ul v-if="probes.length" class="dp-probes">
        <li v-for="p in probes" :key="p.name">
          <span class="c-badge" :class="p.ok ? 'c-badge--ok' : 'c-badge--danger'">{{ p.ok ? '正常' : '异常' }}</span>
          <span class="dp-probe-name">{{ p.name }}</span>
          <span class="c-weak c-num">{{ fmtMs(p.latency_ms) }}</span>
          <span v-if="p.detail" class="c-weak dp-probe-detail">{{ p.detail }}</span>
        </li>
      </ul>
      <p v-else class="c-weak" style="font-size: 12.5px">暂无探测结果（后端未就绪或采集通道未开启）</p>
    </section>

    <section class="c-card">
      <div class="c-card-head">
        <div>
          <h2 class="c-card-title">采集自监控</h2>
          <p class="c-card-sub">
            运维看板自己也要被观测：trace 丢了多少、写库失败多少次、采集器与预警评估报错多少次
          </p>
        </div>
        <RouterLink to="/ops/traces" class="dp-link">查看 trace</RouterLink>
      </div>
      <div class="c-stat-row">
        <StatTile label="已写入 trace" :value="self ? fmtCompact(self.trace_written_total) : '—'" unit="条" />
        <StatTile
          label="丢弃 trace"
          :value="self ? fmtCompact(self.trace_dropped_total) : '—'"
          unit="条"
          :tone="self && self.trace_dropped_total > 0 ? 'warn' : undefined"
          hint="队列满时丢当前，不阻塞业务"
        />
        <StatTile
          label="写库失败"
          :value="self ? fmtCompact(self.trace_write_errors_total) : '—'"
          unit="条"
          :tone="self && self.trace_write_errors_total > 0 ? 'danger' : undefined"
          :hint="self ? `缓冲区 ${self.trace_buffered} 条` : ''"
        />
        <StatTile
          label="预警评估错误"
          :value="self ? fmtCompact(self.ops_alert_eval_errors_total) : '—'"
          unit="次"
          :tone="self && self.ops_alert_eval_errors_total > 0 ? 'danger' : undefined"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.dp-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.dp-stats {
  grid-column: 1 / -1;
}
.dp-link {
  font-size: 12.5px;
  white-space: nowrap;
}
.dp-probes {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.dp-probes li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.dp-probe-name {
  font-weight: 500;
}
.dp-probe-detail {
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
