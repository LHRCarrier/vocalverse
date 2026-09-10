<script setup lang="ts">
/**
 * 工作台 · 运营面板（docs/50 §11.3）。
 *
 * 运营关心的是：**每个内容库各有多少、多少已上架、最近改了哪些**。
 * 「已上架占比」用 F5 横向刻痕行表达（少类目排名 + 单位可数），
 * 不用饼图：4 个类目的占比用横条比用环读得快，而且横条能给绝对数。
 *
 * ⚠️ 每个内容库的读接口**按写方矩阵**逐个指定（docs/50 §3.2）：
 * Python 侧只服务 `library/books`（`services/python/app/console/api/routes/library.py:61`）与
 * `library/media`，歌曲/听力素材/场景在 Java 侧（`consoleApi.listSongs/listMaterials/listScenarios`）。
 * 之前用"不是 Java 就是 Python"的布尔开关，把听力素材与场景也指到了 `opsApi.listBooks`——
 * 两个类目显示的是书籍条数（数据与标题不符，且不会报错）。
 */
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { consoleApi, opsApi, publishEventDetail, publishEventDomain } from '@/api'
import type { PublishEventRow } from '@/api'
import ChartCard from '@/components/charts/ChartCard.vue'
import StackedRungs from '@/components/charts/StackedRungs.vue'
import StatTile from '@/components/common/StatTile.vue'
import { useAsync } from '@/composables/useAsync'
import { fmtDateTime, fmtInt } from '@/utils/format'

interface DomainStat {
  key: string
  label: string
  total: number
  published: number
  permission: string
}

type DomainKey = 'songs' | 'listening-materials' | 'scenarios' | 'books'

const domains = ref<DomainStat[]>([])
const events = useAsync(() => consoleApi.publishEvents({ page_size: 8 }))

/** 域 → 读接口。书籍走 Python，其余三个域走 Java；四个域的行类型不同，这里只需要总数 */
function fetchDomain(
  key: DomainKey,
  query: { page_size: number; status?: string },
): Promise<{ total: number }> {
  if (key === 'songs') return consoleApi.listSongs(query)
  if (key === 'listening-materials') return consoleApi.listMaterials(query)
  if (key === 'scenarios') return consoleApi.listScenarios(query)
  return opsApi.listBooks(query)
}

async function loadDomain(key: DomainKey, label: string, permission: string): Promise<void> {
  try {
    const published = await fetchDomain(key, { page_size: 1, status: 'published' })
    const all = await fetchDomain(key, { page_size: 1 })
    domains.value.push({ key, label, total: all.total, published: published.total, permission })
  } catch {
    // 单个域失败（如权限不足）不该让整块面板垮掉——直接不显示该行
  }
}

onMounted(async () => {
  await Promise.all([
    loadDomain('songs', '歌曲', 'content:song:read'),
    loadDomain('listening-materials', '听力素材', 'content:listening:read'),
    loadDomain('scenarios', '场景', 'content:scenario:read'),
    loadDomain('books', '书籍', 'content:book:read'),
  ])
  void events.run()
})

interface RecentEvent {
  id: number
  at: string
  domain: string
  targetId: string
  from: string
  to: string
  operator: string
}

/** 流水的 domain 由 action 推导、前后状态藏在 detail JSON 里（见 `consoleApi.publishEventDetail`） */
const recent = computed<RecentEvent[]>(() =>
  (events.state.value.data?.items ?? []).map((e: PublishEventRow) => {
    const detail = publishEventDetail(e)
    return {
      id: e.id,
      at: e.createdAt,
      domain: publishEventDomain(e) ?? e.targetType,
      targetId: e.targetId,
      from: detail.prevStatus ?? '—',
      to: detail.nextStatus ?? '—',
      operator: e.operator,
    }
  }),
)
const totalPublished = computed(() => domains.value.reduce((sum, d) => sum + d.published, 0))
</script>

<template>
  <div class="cp-grid">
    <div class="c-stat-row cp-stats">
      <StatTile label="内容总量" :value="fmtInt(domains.reduce((s, d) => s + d.total, 0))" unit="条" hint="歌曲 + 听力素材 + 场景 + 书籍" />
      <StatTile label="已上架" :value="fmtInt(totalPublished)" unit="条" tone="ok" hint="status = published" />
      <StatTile
        label="未上架"
        :value="fmtInt(domains.reduce((s, d) => s + d.total, 0) - totalPublished)"
        unit="条"
        tone="warn"
        hint="草稿或已下架（archived）"
      />
    </div>

    <!-- F7 Stacked Rungs：类目 × 构成（≤4 类 × ≤3 段），同时看总量与已上架占比 -->
    <ChartCard
      title="哪个库还没上齐"
      sub="每个柱 = 一个内容库的总量 · 深色段 = 已上架 · 浅色段 = 草稿或已下架 · 段高 ∝ 条数"
      chart-no="F7"
      template-title="Where each region's revenue sits"
      source="songs / listening-materials / scenarios（Java）· books（Python /library/books）"
      :height="220"
      wide
    >
      <template #default="{ revealed }">
        <StackedRungs
          :categories="domains.map((d) => d.label)"
          :segments="[
            { name: '已上架', values: domains.map((d) => d.published) },
            { name: '未上架', values: domains.map((d) => Math.max(0, d.total - d.published)) },
          ]"
          unit=" 条"
          :revealed="revealed"
        />
        <p v-if="!domains.length" class="c-weak" style="font-size: 12.5px; margin: 0">
          暂无内容统计（权限不足或后端未就绪）
        </p>
      </template>
    </ChartCard>

    <section class="c-card">
      <div class="c-card-head">
        <div>
          <h2 class="c-card-title">最近的上架 / 下架</h2>
          <p class="c-card-sub">
            来自审计流水（admin_audit_logs），因此谁改的、什么时候改的都可查 ·
            内容域由 action 推导、前后状态从 detail 解析（后端不单独返回这三个字段）
          </p>
        </div>
        <RouterLink to="/content/publish-events" class="cp-link">全部流水</RouterLink>
      </div>
      <ul v-if="recent.length" class="cp-events">
        <li v-for="e in recent" :key="e.id">
          <span class="cp-event-time c-num">{{ fmtDateTime(e.at) }}</span>
          <span class="cp-event-main">
            {{ e.domain }} #{{ e.targetId }}
            <span class="c-weak">{{ e.from }} → {{ e.to }}</span>
          </span>
          <span class="c-weak">{{ e.operator }}</span>
        </li>
      </ul>
      <p v-else class="c-weak" style="font-size: 12.5px">暂无上架记录</p>
    </section>
  </div>
</template>

<style scoped>
.cp-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.cp-stats {
  grid-column: 1 / -1;
}
.cp-link {
  font-size: 12.5px;
  white-space: nowrap;
}
.cp-rows {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 11px;
}
.cp-rows li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
}
.cp-row-label {
  width: 64px;
  flex: 0 0 auto;
  color: var(--c-text-2);
}
.cp-row-track {
  position: relative;
  height: 10px;
  border-radius: 999px;
  background: var(--c-surface-sunken);
  overflow: hidden;
  min-width: 10px;
}
.cp-row-fill {
  position: absolute;
  inset: 0 auto 0 0;
  background: var(--c-text);
  border-radius: 999px;
  transition: width var(--vv-t-std) var(--vv-ease-out);
}
.cp-row-value {
  flex: 0 0 auto;
  font-weight: 600;
  white-space: nowrap;
}
.cp-events {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cp-events li {
  display: grid;
  grid-template-columns: 132px 1fr auto;
  gap: 10px;
  align-items: baseline;
  font-size: 12.5px;
}
.cp-event-time {
  color: var(--c-text-3);
  font-size: 11.5px;
}
.cp-event-main {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
