<script setup lang="ts">
/**
 * 移动端 · 我的学习（2026-09-09 组长与组员讨论拍板 v4：重新设计，当前设计作废）
 * 定位修正：学习主页 = 「我的学习」画像总览——一句话结论 + 微识别 + 一张信息图 + 模块列表，
 * 数据细节下沉到模块详情页（/m/learn/:module，手机小屏不挤一页）。
 * 结构（X 式）：
 *   ① 欢迎定位行：Hi 昵称 + 一句话画像（一眼明白的锚点）
 *   ② 识别行（轻量）：LV3 chip + 70/500 XP + 金条 + 🔥12天（不做大卡）
 *   ③ 学习热力图（信息图 · 保留：好看且用户可读；只图 + 右下 +XP）
 *   ④ 模块列表（4 行：我的单词 / 社区足迹 / 我的发音 / 练习情况——每行一句摘要，要细节点进去）
 * 数据口径：progress/auth 真实；热力图/摘要演示帧（M3 接 attempts/埋点聚合）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { track } from '@/api/events'
import { fetchLearnOverview } from '@/api/stats'
import type { LearnOverview } from '@/api/stats'
import { fetchItemsRecommendations } from '@/api/reco'
import type { RecoItem } from '@/api/reco'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { useAuthStore } from '@/stores/auth'
import { useCheckinStore } from '@/stores/checkin'
import { useProgressStore } from '@/stores/progress'
import '@/styles/mobile-uic.css'

const progress = useProgressStore()
const auth = useAuthStore()
const checkin = useCheckinStore()
const router = useRouter()

const displayName = computed(() => auth.me?.nickname ?? auth.me?.username ?? '学习者')

/* ---------- 学习画像（docs/53 P4：真实聚合；加载失败回退空态文案） ---------- */
const learn = ref<LearnOverview | null>(null)
const profileLine = computed(
  () => learn.value?.profile_line ?? '正在读取你的学习画像…',
)
const forecastText = computed(() => {
  const f = learn.value?.forecast
  if (!f?.available) return ''
  const arrow = f.direction === 'up' ? '↑' : f.direction === 'down' ? '↓' : '→'
  return `水平预测：下月综合分 ${f.predicted_overall}（${arrow} ${f.delta}）`
})

async function loadLearn() {
  try {
    learn.value = await fetchLearnOverview()
  } catch {
    /* 画像非关键路径：失败保留占位文案 */
  }
}

/* ---------- 识别行 ---------- */
/* 连续天数 = 真实打卡卡聚合（stores/checkin）；未加载时为 0，不写死演示值 */
const streak = computed(() => checkin.streak)

/* ---------- 为你推荐（docs/53 P3：内容型推荐；曝光服务端落库，点击前端上报） ---------- */
const recoItems = ref<RecoItem[]>([])
const recoGroupId = ref('')

const RECO_KIND_LABEL: Record<RecoItem['kind'], string> = {
  song: '歌曲',
  book: '读物',
  card: '场景卡',
}

function recoTargetPath(item: RecoItem): string {
  if (item.kind === 'song') return '/m/sing'
  if (item.kind === 'book') return `/m/books/${item.id}`
  return '/m/tavern'
}

function openReco(item: RecoItem) {
  void track('recommend_click', {
    recommendGroupId: recoGroupId.value || undefined,
    targetType: item.kind === 'song' ? 'song' : item.kind === 'book' ? 'book' : 'card',
    targetId: item.id,
    payload: { kind: item.kind, rank: recoItems.value.indexOf(item) },
  })
  void router.push(recoTargetPath(item))
}

async function loadReco() {
  try {
    const data = await fetchItemsRecommendations(3)
    recoItems.value = data.items
    recoGroupId.value = data.recommend_group_id
  } catch {
    /* 推荐非关键路径：失败静默（卡片不渲染） */
  }
}

onMounted(() => {
  void checkin.refresh()
  void loadReco()
  void loadLearn()
})

/* ---------- 学习热力图（12 周 × 7 天 · 真实聚合：events 按日计数，docs/53 P4） ---------- */
type HeatCell = { date: Date; level: 0 | 1 | 2 | 3; xp: number }

/** 接口按日返回 [{date, count, level}]；无事件的日子补 0（前端补空格） */
const heatMap = computed(() => {
  const map = new Map<string, { count: number; level: 0 | 1 | 2 | 3 }>()
  for (const cell of learn.value?.heatmap ?? []) {
    map.set(cell.date, { count: cell.count, level: cell.level as 0 | 1 | 2 | 3 })
  }
  return map
})

const localKey = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** 近 12 周网格（列=周 · 行=周一~周日）；今天位于末列 */
function buildWeeks(weeks: number): HeatCell[][] {
  const today = new Date()
  const monday = new Date(today)
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7))
  const start = new Date(monday)
  start.setDate(monday.getDate() - (weeks - 1) * 7)
  const cols: HeatCell[][] = []
  for (let w = 0; w < weeks; w++) {
    const col: HeatCell[] = []
    for (let d = 0; d < 7; d++) {
      const date = new Date(start)
      date.setDate(start.getDate() + w * 7 + d)
      const hit = heatMap.value.get(localKey(date))
      col.push({ date, level: hit?.level ?? 0, xp: hit?.count ?? 0 })
    }
    cols.push(col)
  }
  return cols
}

const weeks = computed(() => buildWeeks(12))
const heatCells = computed(() => weeks.value.flat())
const isToday = (c: HeatCell) => c.date.toDateString() === new Date().toDateString()
const isFuture = (c: HeatCell) => c.date.getTime() > new Date().getTime()
const dateKey = (c: HeatCell) =>
  `${c.date.getFullYear()}-${String(c.date.getMonth() + 1).padStart(2, '0')}-${String(c.date.getDate()).padStart(2, '0')}`

/** 选中格 → 右下角显示该日经验（演示帧详情；默认今天） */
const selected = ref<HeatCell | null>(null)
watch(
  heatCells,
  (cells) => {
    // 数据到达后若当前选中格仍是空态（level 0），默认改选「今天」（首次渲染时接口未回）
    if (selected.value && selected.value.level > 0) return
    selected.value = cells.find(isToday) ?? cells[cells.length - 2] ?? null
  },
  { immediate: true },
)
function pick(cell: HeatCell) {
  selected.value = cell
}
const selectedXpLabel = computed(() => {
  const cell = selected.value
  if (!cell || isFuture(cell) || cell.level === 0) return '未练习'
  return `+${cell.xp} XP`
})

/* ---------- 模块列表（每行 = 图标块 + 名称 + 一句摘要 + 箭头；详情下沉到 /m/learn/:module） ---------- */
const MODULE_META = [
  {
    key: 'words',
    icon: 'bookmark',
    tint: 'var(--u-dark-green)',
    title: '我的单词',
    summary: '阅读查词即收 · 生词本',
    path: '/m/vocab',
  },
  {
    key: 'shelf',
    icon: 'book',
    tint: 'var(--u-dark-navy)',
    title: '书房',
    summary: '英文小说 · 查词 · 听书',
    path: '/m/bookshelf',
  },
  {
    key: 'community',
    icon: 'heart',
    tint: 'var(--u-dark-navy)',
    title: '社区足迹',
    summary: '常逛英语新闻 · 点赞 8 帖',
    path: '/m/learn/community',
  },
  {
    key: 'speaking',
    icon: 'mic',
    tint: 'var(--u-dark-teal)',
    title: '我的发音',
    summary: '发音 82 · 流利 78 · 语法 85',
    path: '/m/learn/speaking',
  },
  {
    key: 'practice',
    icon: 'flame',
    tint: 'var(--u-dark-purple)',
    title: '冒险进度',
    summary: '酒馆剧本 3 场 · 本周 86 分钟',
    path: '/m/learn/practice',
  },
] as const

/** 模块摘要接真（docs/53 P4）：静态元数据（图标/配色/路由）+ 接口 summary */
const moduleList = computed(() =>
  MODULE_META.map((m) => {
    const key = m.key as keyof LearnOverview['modules']
    return { ...m, summary: learn.value?.modules[key]?.summary ?? m.summary }
  }),
)

function openModule(path: string) {
  void router.push(path)
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="学习" />

    <div class="u-learn">
      <!-- ① 欢迎定位行（画像一句话 · 一眼明白的锚点） -->
      <section class="u-learn-greet">
        <p class="u-learn-greet__hi">Hi，{{ displayName }}</p>
        <p class="u-learn-greet__line">{{ profileLine }}</p>
        <p v-if="forecastText" class="u-learn-greet__forecast">{{ forecastText }}</p>
      </section>

      <!-- ② 识别行（轻量：LV chip + XP 条 + 连续天数） -->
      <section class="u-learn-id">
        <b class="u-learn-id__lv">{{ progress.lvLabel }}</b>
        <span class="u-learn-id__xp">{{ progress.xpInLevel }} / {{ progress.nextXp ?? '—' }} XP</span>
        <span class="u-learn-id__bar" role="progressbar" :aria-valuenow="progress.progressPct" aria-valuemin="0" aria-valuemax="100">
          <span class="u-learn-id__fill" :style="{ width: `${progress.progressPct}%` }" />
        </span>
        <button
          class="u-learn-id__streak"
          type="button"
          title="打卡"
          aria-label="打开打卡页"
          @click="openModule('/m/checkin')"
        >
          <MobileIcon name="flame" :size="15" />{{ streak }} 天
        </button>
      </section>

      <!-- ②′ 为你推荐（真实推荐流：内容型基线，docs/53 P3；无数据时不渲染） -->
      <section v-if="recoItems.length" class="u-learn-reco" aria-label="为你推荐">
        <div class="u-learn-reco__head">
          <h2 class="u-learn-reco__title">为你推荐</h2>
          <span class="u-learn-reco__sub">按你的水平与兴趣挑选</span>
        </div>
        <button
          v-for="item in recoItems"
          :key="`${item.kind}-${item.id}`"
          class="u-learn-reco__row"
          type="button"
          @click="openReco(item)"
        >
          <span class="u-learn-reco__kind">{{ RECO_KIND_LABEL[item.kind] }}</span>
          <span class="u-learn-reco__body">
            <span class="u-learn-reco__name">{{ item.title }}</span>
            <span class="u-learn-reco__meta">{{ item.subtitle }} · {{ item.reason }}</span>
          </span>
          <MobileIcon name="arrow" :size="14" />
        </button>
      </section>

      <!-- ③ 学习热力图（信息图 · 只图 + 右下角经验） -->
      <section class="u-learn-heat" aria-label="学习热力图">
        <div class="u-learn-heat__grid">
          <button
            v-for="cell in heatCells"
            :key="dateKey(cell)"
            type="button"
            class="u-learn-heat__cell"
            :class="[
              `lv${cell.level}`,
              { today: isToday(cell), future: isFuture(cell), picked: selected != null && dateKey(cell) === dateKey(selected) },
            ]"
            :disabled="isFuture(cell)"
            :aria-label="`${dateKey(cell)} · ${isFuture(cell) ? '还没到' : cell.level === 0 ? '未练习' : `+${cell.xp} XP`}`"
            @click="pick(cell)"
          />
        </div>
        <div class="u-learn-heat__xp" aria-live="polite">{{ selectedXpLabel }}</div>
      </section>

      <!-- ④ 模块列表（一句话即结论，细节进详情页） -->
      <section class="u-learn-modules" aria-label="我的学习模块">
        <button
          v-for="m in moduleList"
          :key="m.key"
          type="button"
          class="u-learn-module"
          @click="openModule(m.path)"
        >
          <span class="u-learn-module__icon" :style="{ background: m.tint }">
            <MobileIcon :name="m.icon" :size="18" />
          </span>
          <span class="u-learn-module__body">
            <strong class="u-learn-module__title">{{ m.title }}</strong>
            <span class="u-learn-module__summary">{{ m.summary }}</span>
          </span>
          <MobileIcon name="chevron" :size="16" class="u-learn-module__go" />
        </button>
      </section>
    </div>
  </div>
</template>
