<script setup lang="ts">
/**
 * 运维 · 服务总览（docs/50 §10.3 / §8.4）。
 *
 * 这张页面的**唯一口径**：控制台显示的依赖状态必须与容器健康检查一致。
 * 因此数据来自 Python 的 `probe_dependencies()`——与 `/readyz` 共用同一个函数，
 * 而不是控制台自己另写一套探测（否则会出现"看板说健康、compose 说 unhealthy"）。
 *
 * 字段全部按 `services/python/app/console/api/routes/ops.py:87-112` 的 data 直读：
 * `dependencies`（不是 probes）/ `self_monitoring`（不是 selfMonitor）/
 * `concurrency` 是"键=额度名"的对象（ops.py:141-148），不是 `{name,limit,inflight}` 数组。
 */
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'

import { opsApi } from '@/api'
import type { DependencyProbe } from '@/api'
import PageHeader from '@/components/common/PageHeader.vue'
import StatTile from '@/components/common/StatTile.vue'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import { useAsync, useRealtimeRefresh } from '@/composables/useAsync'
import { fmtCompact, fmtDuration, fmtInt, fmtMs } from '@/utils/format'

const overview = useAsync(() => opsApi.overview())

onMounted(() => void overview.run())
useRealtimeRefresh(() => void overview.run(), 15_000)

const data = computed(() => overview.state.value.data)
const deps = computed(() => data.value?.dependencies ?? null)
const probes = computed(() => deps.value?.items ?? [])
const unhealthy = computed(() => probes.value.filter((p) => !p.ok))

/** 后端已给出总体判定（probe.py:33-40），前端不再自己推断，只翻译文案 */
const STATUS_LABEL: Record<DependencyProbe['status'], string> = {
  ready: '全部正常',
  degraded: '降级运行',
  not_ready: '不可用',
}
const statusText = computed(() => (deps.value ? STATUS_LABEL[deps.value.status] : '—'))
const statusTone = computed<'ok' | 'warn' | 'danger' | undefined>(() => {
  if (!deps.value) return undefined
  if (deps.value.status === 'ready') return 'ok'
  return deps.value.status === 'degraded' ? 'warn' : 'danger'
})

const CONCURRENCY_LABELS: Record<string, string> = {
  'http.inflight': 'HTTP 在途请求',
  'asr.limit': 'ASR 并发额度',
  'ise.limit': 'ISE 并发额度',
  'reading_tts.limit': '听书 TTS 并发额度',
  'db.pool.capacity': 'DB 连接池容量',
}
/** 额度类键：只有 `http.inflight` 是"在途"口径，其余是进程内常量（ops.py:132-148） */
type CapacityKey = 'asr.limit' | 'ise.limit' | 'reading_tts.limit' | 'db.pool.capacity'
const CAPACITY_KEYS: CapacityKey[] = [
  'asr.limit',
  'ise.limit',
  'reading_tts.limit',
  'db.pool.capacity',
]

interface CapacityRow {
  key: string
  label: string
  limit: number | null
}

const capacityRows = computed<CapacityRow[]>(() => {
  const c = data.value?.concurrency
  if (!c) return []
  return CAPACITY_KEYS.map((key) => ({ key, label: CONCURRENCY_LABELS[key] ?? key, limit: c[key] }))
})

/** 额度最小的一环 = 同等流量下最先排队的环节（在途只有 HTTP 有口径，故按额度排序） */
const tightest = computed(() => {
  const rows = capacityRows.value.filter((r) => typeof r.limit === 'number' && r.limit > 0)
  if (!rows.length) return null
  return rows.reduce((a, b) => ((b.limit as number) < (a.limit as number) ? b : a))
})
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="服务总览"
      desc="依赖健康、并发额度与采集自监控。依赖探测与容器健康检查同源，显示不一致即为缺陷。"
    />

    <AsyncBlock
      :loading="overview.state.value.loading"
      :error="overview.state.value.error"
      :error-code="overview.state.value.errorCode"
      :empty="!data"
      empty-text="采集通道未开启或后端未就绪"
      empty-hint="检查 APP_OPS_TELEMETRY_ENABLED 与 Python 服务监听 8000"
      :min-height="220"
    >
      <div v-if="data" class="ov">
        <div class="c-stat-row">
          <StatTile
            :label="`服务状态（${data.app_env}）`"
            :value="statusText"
            :tone="statusTone"
            :hint="`共 ${probes.length} 项依赖，${unhealthy.length} 项异常`"
          />
          <StatTile
            label="运行时长"
            :value="fmtDuration(data.uptime_s)"
            :hint="`采集间隔 ${data.collector.interval_s}s · 采集${data.collector.enabled ? '已开启' : '已关闭'}`"
          />
          <StatTile
            label="版本"
            :value="data.version"
            :hint="`LLM trace ${data.flags.llm_trace_enabled ? '开启' : '关闭'} · 内容捕获${data.flags.llm_trace_content_capture ? '开启' : '关闭'}`"
          />
          <StatTile
            label="额度最紧的一环"
            :value="tightest ? fmtInt(tightest.limit) : '—'"
            :hint="tightest ? `${tightest.label}（额度最小的环节最先排队）` : '本进程没有登记信号量额度'"
          />
        </div>

        <section class="c-card">
          <div class="c-card-head">
            <div>
              <h2 class="c-card-title">依赖探测</h2>
              <p class="c-card-sub">
                每项含一次真实调用（不是"配置存在即算健康"——历史上 redis_available 恒返回 true 就是这类假信号） ·
                与 <code>/readyz</code> 同源 · 探测于 {{ deps ? new Date(deps.checked_at).toLocaleString('zh-CN') : '—' }}
              </p>
            </div>
          </div>
          <ul v-if="probes.length" class="ov-probes">
            <li v-for="p in probes" :key="p.name">
              <span class="ov-dot" :class="p.ok ? 'ov-dot--ok' : 'ov-dot--bad'" aria-hidden="true" />
              <span class="ov-probe-name">
                {{ p.name }}
                <em class="ov-probe-req">{{ p.required ? '必需' : '可降级' }}</em>
              </span>
              <span class="c-num c-weak ov-probe-latency">{{ fmtMs(p.latency_ms) }}</span>
              <span class="ov-probe-detail" :class="p.ok ? 'c-weak' : 'ov-probe-detail--bad'">
                {{ p.detail }}
              </span>
            </li>
          </ul>
          <p v-else class="c-weak" style="font-size: 12.5px">没有可探测的依赖</p>
        </section>

        <section class="c-card">
          <div class="c-card-head">
            <div>
              <h2 class="c-card-title">并发额度与在途</h2>
              <p class="c-card-sub">
                {{ data.concurrency.note }}
              </p>
            </div>
            <RouterLink to="/ops/metrics" class="ov-link">看时序</RouterLink>
          </div>
          <ul v-if="capacityRows.length" class="ov-conc">
            <li v-for="row in capacityRows" :key="row.key">
              <span class="ov-conc-label">{{ row.label }}</span>
              <code class="c-mono ov-conc-key">{{ row.key }}</code>
              <span class="c-num ov-conc-value">{{ row.limit === null ? '—' : fmtInt(row.limit) }}</span>
            </li>
          </ul>
          <p v-if="data.concurrency['db.pool.capacity'] === null" class="c-weak" style="font-size: 11.5px">
            DB 连接池容量读取失败（后端返回 null）——不是 0，故显示为「—」。
          </p>
          <p class="c-weak" style="font-size: 11.5px; margin-top: 8px">
            在途口径只有 <code>http.inflight</code>（当前 {{ fmtInt(data.concurrency['http.inflight']) }}）；
            其余是进程内常量额度，不代表"已用多少"。
          </p>
        </section>

        <section class="c-card">
          <div class="c-card-head">
            <div>
              <h2 class="c-card-title">采集自监控</h2>
              <p class="c-card-sub">
                采集有界队列满时**丢当前、不阻塞业务**；丢了多少必须可见，否则"trace 变少"会被误读成"没调用"
              </p>
            </div>
            <RouterLink to="/ops/traces" class="ov-link">查看 trace</RouterLink>
          </div>
          <div class="c-stat-row">
            <StatTile
              label="已写入"
              :value="fmtCompact(data.self_monitoring.trace_written_total)"
              unit="条"
              :hint="`写库失败 ${fmtInt(data.self_monitoring.trace_write_errors_total)} 条 · 缓冲区 ${fmtInt(data.self_monitoring.trace_buffered)} 条`"
            />
            <StatTile
              label="已丢弃"
              :value="fmtCompact(data.self_monitoring.trace_dropped_total)"
              unit="条"
              :tone="data.self_monitoring.trace_dropped_total > 0 ? 'warn' : undefined"
            />
            <StatTile
              label="采集器错误"
              :value="fmtCompact(data.self_monitoring.metric_collector_errors_total)"
              unit="次"
              :tone="data.self_monitoring.metric_collector_errors_total > 0 ? 'danger' : undefined"
            />
            <StatTile
              label="预警评估错误"
              :value="fmtCompact(data.self_monitoring.ops_alert_eval_errors_total)"
              unit="次"
              :tone="data.self_monitoring.ops_alert_eval_errors_total > 0 ? 'danger' : undefined"
            />
          </div>
        </section>

        <p class="ov-foot c-weak">
          数据来自 <code>/api/v1/console/ops/overview</code> ·
          指标按 60s 一桶采集、保留 7 天 ·
          时序查询按 step 在服务端二次聚合，不把 7 天原始桶一次性回传
        </p>
      </div>
    </AsyncBlock>
  </div>
</template>

<style scoped>
.ov {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.ov-link {
  font-size: 12.5px;
  white-space: nowrap;
}
.ov-probes {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.ov-probes li {
  display: grid;
  grid-template-columns: 8px 200px 62px 1fr;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.ov-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.ov-dot--ok {
  background: var(--c-ok);
}
.ov-dot--bad {
  background: var(--c-danger);
}
.ov-probe-name {
  font-weight: 500;
}
.ov-probe-req {
  font-style: normal;
  font-size: 10.5px;
  color: var(--c-text-3);
  margin-left: 5px;
}
.ov-probe-latency {
  text-align: right;
  font-size: 11.5px;
}
.ov-probe-detail {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ov-probe-detail--bad {
  color: var(--c-danger);
}
.ov-conc {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ov-conc li {
  display: grid;
  grid-template-columns: 168px 1fr 90px;
  align-items: baseline;
  gap: 10px;
  font-size: 12.5px;
}
.ov-conc-label {
  color: var(--c-text-2);
}
.ov-conc-key {
  font-size: 11px;
  color: var(--c-text-3);
}
.ov-conc-value {
  text-align: right;
  font-weight: 600;
}
.ov-foot {
  margin: 4px 0 0;
  font-size: 11px;
}
.ov-foot code {
  font-family: var(--vv-font-mono);
}
</style>
