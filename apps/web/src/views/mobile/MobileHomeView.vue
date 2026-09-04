<script setup lang="ts">
/**
 * 移动端 · 今日学习（首页）—— v3.1 样板（docs/31 §5.1 + pages/home.md）
 *
 * 层级金字塔（UI 即信息）：
 *  深蓝渐变焦点卡（今日任务 · 唯一记忆点 + 白色 CTA + 声波装饰）
 *    → 统计白卡（12 灰标签 / 24 粗数字；绿=成绩、黄星=激励）
 *    → 灰轨白 pill 分段（材质派 + 选中加粗双信号）
 *    → 中性图标块列表（数值列文字级蓝）→ 底部浮动 Tab。
 * 字级：12/14/16/24 四档；间距 8/16/24/32；单字体 Plus Jakarta Sans。
 * 数据口径：【占位·M3】统计/打卡/会话列表为演示帧值；真实可用：问候名 + CTA 跳转 + 会话卡跳转。
 */
import { computed, ref } from 'vue'

import { useAuthStore } from '@/stores/auth'

import ArtCalendar from '@/components/mobile/ArtCalendar.vue'
import IconBriefcase from '~icons/tabler/briefcase'
import IconChartBar from '~icons/tabler/chart-bar'
import IconCheck from '~icons/tabler/check'
import IconCoffee from '~icons/tabler/coffee'
import IconFlame from '~icons/tabler/flame'
import IconHeadphones from '~icons/tabler/headphones'
import IconMicrophone from '~icons/tabler/microphone'
import IconMusic from '~icons/tabler/music'
import IconStarFilled from '~icons/tabler/star-filled'
import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import '@/styles/mobile-soft.css'

const auth = useAuthStore()

/* ---------- 问候（真实账户） ---------- */
function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
}

const displayName = computed(() => auth.me?.nickname ?? auth.me?.username ?? '同学')
const avatarLetter = computed(() => displayName.value.slice(0, 1).toUpperCase())

/* ---------- 分段筛选（滑块 translateX，不重排） ---------- */
type Tab = 'all' | 'speaking' | 'singing'

const tab = ref<Tab>('all')

const tabs: { key: Tab; label: string; icon: typeof IconChartBar }[] = [
  { key: 'all', label: '全部', icon: IconChartBar },
  { key: 'speaking', label: '口语', icon: IconMicrophone },
  { key: 'singing', label: '唱歌', icon: IconMusic },
]

const tabIndex = computed(() => tabs.findIndex((t) => t.key === tab.value))

/* ---------- 最近练习（【占位·M3】演示帧数据，接入后替换） ---------- */
interface Session {
  id: number
  kind: 'speaking' | 'singing'
  icon: typeof IconCoffee
  title: string
  sub: string
  value: string
  valueInk?: boolean
  badge: { text: string; variant: 'success' | 'star' | 'neutral' }
}

const sessions: Session[] = [
  {
    id: 1,
    kind: 'speaking',
    icon: IconCoffee,
    title: '情景对话 · 咖啡店点单',
    sub: '今天 9:30 · 8 轮 · 用时 3 分 12 秒',
    value: '86.4',
    badge: { text: '完成', variant: 'success' },
  },
  {
    id: 2,
    kind: 'singing',
    icon: IconMusic,
    title: '跟唱 · Perfect Night',
    sub: '昨天 20:15 · 跟唱 2 遍 · 音准 88',
    value: '88.1',
    badge: { text: '新纪录', variant: 'star' },
  },
  {
    id: 3,
    kind: 'speaking',
    icon: IconBriefcase,
    title: '情景对话 · 面试自我介绍',
    sub: '9 月 12 日 · 6 轮 · 中级难度',
    value: '79.8',
    valueInk: true,
    badge: { text: '待提升', variant: 'neutral' },
  },
  {
    id: 4,
    kind: 'singing',
    icon: IconHeadphones,
    title: '跟唱 · Yesterday Once More',
    sub: '9 月 10 日 · 跟唱 1 遍 · 节奏 91',
    value: '91.5',
    badge: { text: '优秀', variant: 'success' },
  },
]

const visibleSessions = computed(() =>
  tab.value === 'all' ? sessions : sessions.filter((s) => s.kind === tab.value),
)

/* ---------- 今日任务（【占位·M3】学习计划 P1 演示帧） ---------- */
const planSteps = [
  { text: '场景对话 · 1 轮', done: false },
  { text: '跟唱练习 · 1 遍', done: true },
] as const
</script>

<template>
  <div class="s-phone">
    <div class="s-page">
      <!-- 身份：问候 + 头像（真实账户名）；字级 24+12 -->
      <header class="s-head">
        <div>
          <h1 class="s-h1">{{ greeting() }}，{{ displayName }}</h1>
          <p class="s-caption" style="margin-top: 4px">今天练完这 1 次，就能保住连胜。</p>
        </div>
        <div class="s-avatar" aria-label="头像">{{ avatarLetter }}</div>
      </header>

      <!-- 激励：打卡徽章（黄色=激励，全屏唯一黄） -->
      <div class="s-streak">
        <IconFlame style="width: 16px; height: 16px" />
        连续打卡 12 天 · 本周 5/7
      </div>

      <!-- 焦点：深蓝渐变任务卡（唯一记忆点；白 CTA；装饰声波） -->
      <section class="s-plan" aria-label="今日练习">
        <span class="s-plan__badge"><IconFlame style="width: 14px; height: 14px" />今日</span>
        <div class="s-plan__title">今日练习</div>
        <div class="s-plan__steps">
          <template v-for="s in planSteps" :key="s.text">
            <div class="s-plan__step" :class="{ 'is-done': s.done }">
              <span class="s-plan__dot" :class="{ 'is-done': s.done }" aria-hidden="true" />
              {{ s.text }}
              <IconCheck
                v-if="s.done"
                style="width: 14px; height: 14px; color: var(--s-success)"
              />
            </div>
          </template>
        </div>
        <RouterLink to="/m/chat" class="s-btn s-btn--white s-btn--block">
          <IconMicrophone style="width: 18px; height: 18px" />
          开始今日练习
        </RouterLink>
        <ArtCalendar class="s-plan__art" aria-hidden="true" />
      </section>

      <!-- 次级数据：统计白卡（12 灰标签 / 24 粗数字；绿=成绩、黄星=激励） -->
      <section class="s-stats s-card" aria-label="学习统计">
        <div>
          <div class="s-stat-label">累计轮数</div>
          <div class="s-stat-value">38</div>
        </div>
        <div>
          <div class="s-stat-label">平均分</div>
          <div class="s-stat-value s-stat-value--score">86.4</div>
        </div>
        <div>
          <div class="s-stat-label">连续天数</div>
          <div class="s-stat-value s-stat-value--star">
            <IconStarFilled style="width: 16px; height: 16px" />12
          </div>
        </div>
      </section>

      <!-- 筛选：灰轨 + 白色浮起 pill（选中加粗=双信号） -->
      <div class="s-segment" role="tablist" aria-label="练习类型筛选">
        <span
          class="s-segment__thumb"
          :style="{ transform: `translateX(${tabIndex * 100}%)` }"
          aria-hidden="true"
        />
        <button
          v-for="t in tabs"
          :key="t.key"
          type="button"
          role="tab"
          :aria-selected="tab === t.key"
          class="s-segment__btn"
          :class="{ active: tab === t.key }"
          @click="tab = t.key"
        >
          <component :is="t.icon" style="width: 16px; height: 16px" />{{ t.label }}
        </button>
      </div>

      <!-- 轨迹：最近练习（中性图标块 + 数值列文字级蓝） -->
      <h3 class="s-h3 s-section">最近练习</h3>
      <template v-for="s in visibleSessions" :key="s.id">
        <RouterLink
          :to="s.kind === 'speaking' ? '/m/chat' : '/m/sing'"
          class="s-row"
          :aria-label="`查看 ${s.sub}`"
        >
          <span
            class="s-row__icon"
            :class="s.kind === 'speaking' ? 's-row__icon--speaking' : 's-row__icon--singing'"
          >
            <component :is="s.icon" aria-hidden="true" />
          </span>
          <span class="s-row__main">
            <span class="s-row__title">{{ s.title }}</span>
            <span class="s-row__sub">{{ s.sub }}</span>
          </span>
          <span class="s-row__right">
            <span class="s-row__value" :class="{ 's-row__value--ink': s.valueInk }">{{ s.value }}</span>
            <span class="s-badge" :class="`s-badge--${s.badge.variant}`">{{ s.badge.text }}</span>
          </span>
        </RouterLink>
      </template>

      <div v-if="!visibleSessions.length" class="s-empty">
        <div class="s-empty__icon"><IconMicrophone style="width: 30px; height: 30px" /></div>
        <div class="s-empty__title">还没有记录</div>
        <div class="s-empty__sub">完成第一次练习后，这里会展示你的成长轨迹。</div>
      </div>

      <p class="s-note" style="margin-top: 24px">
        统计与列表为演示帧数据，M3 接入真实会话记录后自动替换。
      </p>
    </div>

    <MobileTabBar />
  </div>
</template>
