<script setup lang="ts">
/**
 * 审核 · 待审队列（docs/50 §6.2 状态机、§10.2 端点、§11.3 布局）。
 *
 * 页面主张：**审核员的产出是"处置"，不是"浏览"**。所以
 * 1. 顶部只给四个数（积压 / 升级件 / 今日已处置 / 今日驳回）与一张队列趋势图，
 *    让他先知道"今天还剩多少、积压有没有在缩小"；
 * 2. 列表把「决定」做成行内主操作——决定弹窗里摆出内容快照与每个决定的真实后果（§6.2 映射表）；
 * 3. 认领（assign）与决定（decide）都是写操作，一并挂在 `moderation:decide` 后面。
 *
 * 并发口径：两个审核员同时点「决定」时，服务端条件 UPDATE 只让一个成功，另一个收 46010
 * （§6.2 竞态消除）。这里把 46010 当成**预期内结果**处理：提示"该单已被其他人处理，请刷新"并重新拉列表。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { NAlert, NButton, NDataTable, NSelect, useMessage } from 'naive-ui'
import { useRoute } from 'vue-router'

import { ERR, consoleApi } from '@/api'
import type { ModerationCaseRow, ModerationTargetType } from '@/api'
import ChartCard from '@/components/charts/ChartCard.vue'
import HairlineLine from '@/components/charts/HairlineLine.vue'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatTile from '@/components/common/StatTile.vue'
import { useAsync } from '@/composables/useAsync'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { fmtCompact, fmtInt } from '@/utils/format'

import DecisionDialog from './DecisionDialog.vue'
import {
  CASE_STATUS_OPTIONS,
  PRIORITY_OPTIONS,
  TARGET_TYPE_OPTIONS,
  describeFailure,
  failureLines,
  pickCase,
} from './moderationMeta'
import { buildQueueColumns } from './queueColumns'

const route = useRoute()
const auth = useAuthStore()
const message = useMessage()

const stats = useAsync(() => consoleApi.moderationStats(30))
const cases = usePagedList<
  ModerationCaseRow,
  { status: string; targetType: string; priority: string; assigneeId: string }
>(
  (q) =>
    consoleApi.listCases({
      page: q.page,
      page_size: q.page_size,
      status: q.status || undefined,
      targetType: (q.targetType || undefined) as ModerationTargetType | undefined,
      priority: q.priority ? Number(q.priority) : undefined,
      assigneeId: q.assigneeId ? Number(q.assigneeId) : undefined,
    }),
  { status: 'pending', targetType: '', priority: '', assigneeId: '' },
)

const meId = computed(() => auth.profile?.adminUserId ?? null)
const canDecide = computed(() => auth.hasPermission('moderation:decide'))
const s = computed(() => stats.state.value.data)
const trendLabels = computed(() => (s.value?.trend ?? []).map((p) => p.date.slice(5)))

const assigneeOptions = computed(() => [
  { label: '全部认领人', value: '' },
  { label: '只看我认领的', value: meId.value === null ? '-1' : String(meId.value) },
])

/** 从举报处理页带过来的审核单 id（没有 per-case 路由，故用查询参数当"定位提示"，不新造路由） */
const hintCaseId = ref<number | null>(null)
const hintCase = ref<ModerationCaseRow | null>(null)

const dialogShow = ref(false)
const current = ref<ModerationCaseRow | null>(null)

function openDecision(row: ModerationCaseRow): void {
  current.value = row
  dialogShow.value = true
}

/** 举报处理页的「一键跳到该单」落点：这里直接把该单取出来打开决定弹窗 */
async function openFromQuery(): Promise<void> {
  const raw = route.query.caseId
  const id = Number(Array.isArray(raw) ? raw[0] : raw)
  if (!Number.isFinite(id) || id <= 0) return
  hintCaseId.value = id
  try {
    const row = pickCase(await consoleApi.getCase(id))
    if (!row) {
      message.warning(`审核单 #${id} 的返回结构无法识别，请在列表中查找`)
      return
    }
    hintCase.value = row
    openDecision(row)
  } catch (err) {
    message.error(describeFailure(err).message)
  }
}

onMounted(async () => {
  await Promise.all([stats.run(), cases.load()])
  await openFromQuery()
})

// 同路由带新 caseId 再跳一次时（组件不重建）也要能定位——查询参数就是本页的"定位提示"通道
watch(
  () => route.query.caseId,
  () => void openFromQuery(),
)

/** 46010 是预期的并发结果，不是故障：提示刷新并重拉；其余按错误码补足可操作信息 */
function reportError(err: unknown): void {
  const failure = describeFailure(err)
  if (failure.code === ERR.CASE_STATE_CONFLICT) {
    message.warning('该单已被其他人处理，请刷新')
    void cases.load()
    return
  }
  message.error(failureLines(failure).join('；'))
}

async function toggleAssign(row: ModerationCaseRow): Promise<void> {
  const me = meId.value
  if (me === null) {
    message.warning('当前账号档案尚未加载，无法认领')
    return
  }
  const mine = row.assigneeId === me
  try {
    await consoleApi.assignCase(row.id, mine ? null : me)
    message.success(mine ? `已取消认领 单 #${row.id}` : `已认领 单 #${row.id}`)
    await cases.load()
  } catch (err) {
    reportError(err)
  }
}

async function onDecided(): Promise<void> {
  hintCaseId.value = null
  hintCase.value = null
  await Promise.all([cases.load(), stats.run()])
}

const columns = computed(() =>
  buildQueueColumns({
    meId: () => meId.value,
    canDecide: () => canDecide.value,
    assign: (row) => void toggleAssign(row),
    decide: openDecision,
  }),
)

function rowProps(row: ModerationCaseRow): { class: string } {
  return { class: row.id === hintCaseId.value ? 'mq-row--hint' : '' }
}
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="待审队列"
      desc="按优先级从高到低处理。隐藏与删除会让内容对用户立即不可见（作者也一样），决定前请核对内容快照与原因码。"
    >
      <template #actions>
        <span v-if="!canDecide" class="c-badge c-badge--muted">只读（需 moderation:decide）</span>
      </template>
    </PageHeader>

    <n-alert v-if="hintCaseId !== null" class="mq-hint" type="info" title="从举报处理跳转而来">
      <span>已定位到审核单 #{{ hintCaseId }}——决定弹窗已打开，列表中该行也已标记。</span>
      <n-button
        v-if="hintCase"
        class="mq-hint-btn"
        size="tiny"
        quaternary
        type="primary"
        @click="openDecision(hintCase)"
      >
        重新打开该单
      </n-button>
    </n-alert>

    <AsyncBlock
      :loading="stats.state.value.loading"
      :error="stats.state.value.error"
      :error-code="stats.state.value.errorCode"
      :empty="!s"
      empty-text="暂无队列统计"
      :min-height="120"
    >
      <div class="c-stat-row">
        <StatTile
          label="待处理"
          :value="s ? fmtInt(s.pending) : '—'"
          unit="单"
          :tone="s && s.pending > 0 ? 'warn' : 'ok'"
          hint="队列里还没处置的单"
        />
        <StatTile
          label="已升级"
          :value="s ? fmtInt(s.escalated) : '—'"
          unit="单"
          :tone="s && s.escalated > 0 ? 'danger' : undefined"
          hint="需要更高权限判断"
        />
        <StatTile
          label="今日已处置"
          :value="s ? fmtInt(s.approvedToday) : '—'"
          unit="单"
          hint="通过 / 隐藏 / 删除合计"
        />
        <StatTile
          label="今日驳回"
          :value="s ? fmtInt(s.rejectedToday) : '—'"
          unit="单"
          hint="举报不成立"
        />
      </div>

      <div class="mq-chart">
        <ChartCard
          title="积压有没有在缩小"
          sub="每日新建 / 已处置 / 驳回 · 近 30 天 · 单量按「建单时间」归日"
          chart-no="F3"
          template-title="Concurrent users, filled with days"
          source="moderation_cases + admin_audit_logs · /api/v1/console/moderation/stats"
          :height="190"
          wide
        >
          <template #default="{ revealed }">
            <HairlineLine
              :labels="trendLabels"
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
      </div>
    </AsyncBlock>

    <section class="c-card mq-card">
      <div class="c-card-head">
        <div>
          <h2 class="c-card-title">待审单</h2>
          <p class="c-card-sub">
            默认只看待处理；升级件排在最高优先级（服务端把 priority 提到 1），不会被普通审核员误关
          </p>
        </div>
        <div class="mq-filters">
          <n-select
            v-model:value="cases.filters.value.status"
            class="mq-filter"
            size="small"
            :options="[{ label: '全部状态', value: '' }, ...CASE_STATUS_OPTIONS]"
            @update:value="cases.applyFilters({})"
          />
          <n-select
            v-model:value="cases.filters.value.targetType"
            class="mq-filter"
            size="small"
            :options="[{ label: '全部目标', value: '' }, ...TARGET_TYPE_OPTIONS]"
            @update:value="cases.applyFilters({})"
          />
          <n-select
            v-model:value="cases.filters.value.priority"
            class="mq-filter mq-filter--sm"
            size="small"
            :options="[{ label: '全部优先级', value: '' }, ...PRIORITY_OPTIONS]"
            @update:value="cases.applyFilters({})"
          />
          <n-select
            v-model:value="cases.filters.value.assigneeId"
            class="mq-filter"
            size="small"
            :options="assigneeOptions"
            :disabled="meId === null"
            @update:value="cases.applyFilters({})"
          />
          <n-button size="small" quaternary @click="cases.load()">刷新</n-button>
        </div>
      </div>

      <AsyncBlock
        :loading="cases.loading.value"
        :error="cases.error.value"
        :error-code="cases.errorCode.value"
        :empty="!cases.items.value.length"
        empty-text="没有符合条件的待审单"
        empty-hint="换个筛选条件看看；举报处理页可以把举报受理成新的审核单"
        :min-height="200"
      >
        <n-data-table
          :columns="columns"
          :data="cases.items.value"
          :row-key="(row: ModerationCaseRow) => row.id"
          :row-props="rowProps"
          size="small"
          :bordered="false"
        />
        <div class="mq-pager">
          <span class="c-weak">共 {{ fmtInt(cases.total.value) }} 条</span>
          <n-button
            size="small"
            quaternary
            :disabled="cases.page.value <= 1"
            @click="cases.goPage(cases.page.value - 1)"
          >
            上一页
          </n-button>
          <span class="c-num">{{ cases.page.value }} / {{ cases.pageCount.value }}</span>
          <n-button
            size="small"
            quaternary
            :disabled="cases.page.value >= cases.pageCount.value"
            @click="cases.goPage(cases.page.value + 1)"
          >
            下一页
          </n-button>
        </div>
      </AsyncBlock>
    </section>

    <DecisionDialog v-model:show="dialogShow" :item="current" @done="onDecided" />
  </div>
</template>

<style scoped>
.mq-card {
  margin-top: 14px;
}
.mq-chart {
  margin-top: 14px;
}
.mq-hint {
  margin-bottom: 14px;
  border-radius: var(--c-ctl-radius);
}
.mq-hint-btn {
  margin-left: 8px;
}
.mq-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.mq-filter {
  width: 138px;
}
.mq-filter--sm {
  width: 128px;
}
.mq-target-id {
  margin-left: 5px;
  font-size: 12px;
  color: var(--c-text-2);
}
.mq-snippet {
  display: block;
  max-width: 100%;
  font-size: 12px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.mq-actions {
  display: inline-flex;
  gap: 2px;
}
.mq-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 10px;
  font-size: 12.5px;
}
:deep(.mq-row--hint td) {
  background: var(--c-primary-soft);
}
</style>
