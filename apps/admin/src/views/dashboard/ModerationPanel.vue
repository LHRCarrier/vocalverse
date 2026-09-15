<script setup lang="ts">
/**
 * 工作台 · 审核面板（docs/50 §11.3）。
 *
 * 审核员第一眼要的是：**积压多少 / 有没有升级件 / 今天处置了多少**。
 * 队列趋势用 F2 发丝线（逐日读数），处置构成用计数列表——
 * 这里刻意不塞环形图：3–4 个类目的计数用文字列表比一个环读得更快，
 * 环形留给「审核详情页」（docs/50 §12.2 分工）。
 */
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'

import { consoleApi } from '@/api'
import ChartCard from '@/components/charts/ChartCard.vue'
import HairlineLine from '@/components/charts/HairlineLine.vue'
import TickDonut from '@/components/charts/TickDonut.vue'
import StatTile from '@/components/common/StatTile.vue'
import { useAsync, useRealtimeRefresh } from '@/composables/useAsync'
import { fmtCompact, fmtInt } from '@/utils/format'

const stats = useAsync(() => consoleApi.moderationStats(30))

onMounted(() => {
  void stats.run()
})
useRealtimeRefresh(() => void stats.run(), 30_000)

const s = computed(() => stats.state.value.data)
const labels = computed(() => (s.value?.trend ?? []).map((p) => p.date.slice(5)))

const DECISION_LABEL: Record<string, string> = {
  approve: '通过（内容保留）',
  hide: '隐藏',
  delete: '删除',
  reject: '驳回',
  escalate: '升级',
}

/**
 * F4 Tick Donut 的数据。
 * **为什么不是 L14 Hundred Field**：L14 的密度来自「1 点 = 1 个百分点」的单位分解，
 * 而处置次数是**可数的真实单量**（几十到几百），摊成 100 个点等于假装只有 100 件
 * （SKILL §3「只摊诚实单位，不编造个体」）。所以这里用环形 + 逐段标数。
 */
const donutItems = computed(() =>
  (s.value?.decisions ?? []).map((d) => ({
    label: DECISION_LABEL[d.decision] ?? d.decision,
    value: d.count,
  })),
)
</script>

<template>
  <div class="mp-grid">
    <div class="c-stat-row mp-stats">
      <StatTile
        label="待处理"
        :value="s ? fmtInt(s.pending) : '—'"
        unit="单"
        :tone="s && s.pending > 0 ? 'warn' : 'ok'"
        hint="队列里还没人认领的单"
        :loading="stats.state.value.loading"
      />
      <StatTile
        label="已升级"
        :value="s ? fmtInt(s.escalated) : '—'"
        unit="单"
        :tone="s && s.escalated > 0 ? 'danger' : undefined"
        hint="需要更高权限判断"
        :loading="stats.state.value.loading"
      />
      <StatTile
        label="今日已处置"
        :value="s ? fmtInt(s.approvedToday) : '—'"
        unit="单"
        hint="通过 / 隐藏 / 删除合计"
        :loading="stats.state.value.loading"
      />
      <StatTile
        label="今日驳回"
        :value="s ? fmtInt(s.rejectedToday) : '—'"
        unit="单"
        hint="举报不成立"
        :loading="stats.state.value.loading"
      />
    </div>

    <ChartCard
      title="积压有没有在缩小"
      sub="每日新建 / 已处置 / 驳回 · 近 30 天 · 单量按「建单时间」归日"
      chart-no="F3"
      template-title="Concurrent users, filled with days"
      source="moderation_cases + admin_audit_logs · /api/v1/console/moderation/stats"
      :height="200"
      wide
    >
      <template #default="{ revealed }">
        <HairlineLine
          :labels="labels"
          :series="[
            { name: '新建', values: (s?.trend ?? []).map((p) => p.pending), tone: 0 },
            { name: '已处置', values: (s?.trend ?? []).map((p) => p.approved), tone: 2 },
            { name: '驳回', values: (s?.trend ?? []).map((p) => p.rejected), tone: 4 },
          ]"
          unit=" 单"
          :format="(v) => fmtCompact(v)"
          :revealed="revealed"
        />
      </template>
    </ChartCard>

    <ChartCard
      title="处置构成：哪种处置用得最多"
      sub="近 30 天各类决定的数量 · 段数 ≤6 · 「隐藏」与「删除」都会让内容对用户不可见"
      chart-no="F4"
      template-title="Where the traffic comes from"
      source="admin_audit_logs（决定快照） · /api/v1/console/moderation/stats"
      :height="220"
    >
      <template #default="{ revealed }">
        <TickDonut
          :items="donutItems"
          unit=""
          center-label="次处置"
          :revealed="revealed"
        />
      </template>
    </ChartCard>

    <ChartCard
      title="从哪开始"
      sub="按优先级从高到低处理；升级件不会被普通审核员误关"
      chart-no="—"
      template-title="（导航卡，非数据图）"
      source="—"
      :height="180"
    >
      <template #default>
        <div class="mp-links">
          <RouterLink class="mp-link-card" to="/moderation/queue">
            <span class="mp-link-title">待审队列</span>
            <span class="mp-link-desc">按优先级排序，可认领与批注</span>
          </RouterLink>
          <RouterLink class="mp-link-card" to="/moderation/reports">
            <span class="mp-link-title">举报处理</span>
            <span class="mp-link-desc">用户举报逐条判定，可合并为审核单</span>
          </RouterLink>
          <RouterLink class="mp-link-card" to="/moderation/actions">
            <span class="mp-link-title">处置记录</span>
            <span class="mp-link-desc">全部决定的审计流水（谁在什么时候处置了什么）</span>
          </RouterLink>
        </div>
      </template>
    </ChartCard>
  </div>
</template>

<style scoped>
.mp-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.mp-stats {
  grid-column: 1 / -1;
}
.mp-link {
  font-size: 12.5px;
  white-space: nowrap;
}
.mp-bars {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.mp-bars li {
  display: grid;
  grid-template-columns: 116px 1fr 44px;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
}
.mp-bar-label {
  color: var(--c-text-2);
}
.mp-bar {
  height: 8px;
  border-radius: 999px;
  background: var(--c-surface-sunken);
  overflow: hidden;
}
.mp-bar i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--c-text);
  transition: width var(--vv-t-std) var(--vv-ease-out);
}
.mp-bar-value {
  text-align: right;
  font-weight: 600;
}
.mp-links {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.mp-link-card {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px 14px;
  border: 1px solid var(--c-border);
  border-radius: var(--c-ctl-radius);
  color: var(--c-text);
  transition: border-color var(--vv-t-micro) var(--vv-ease-out), background var(--vv-t-micro) var(--vv-ease-out);
}
.mp-link-card:hover {
  border-color: var(--c-primary);
  background: var(--c-primary-soft);
}
.mp-link-title {
  font-size: 13.5px;
  font-weight: 600;
}
.mp-link-desc {
  font-size: 11.5px;
  color: var(--c-text-2);
}
</style>
