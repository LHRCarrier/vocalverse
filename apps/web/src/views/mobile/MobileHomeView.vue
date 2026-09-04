<script setup lang="ts">
/**
 * 移动端 · 今日学习（首页）—— v6 clean 重设计（docs/31 §5.1 + pages/home.md v6）
 *
 * 设计语言 = 与登录页同源（user 验收的 bad-cheetah-74）：
 *  - 灰底白卡 / 1.5px #ECEDEC 细边 / 圆角 20-10 / 无硬阴影
 *  - 炭黑按钮（与 Sign In 同款）＝ 唯一行动；蓝 #2D79F3 ＝ 交互·链接·选中
 *  - 焦点 = 今日任务白卡（含炭黑主按钮）→ 统计 → 白 pill 分段（蓝边选中）→ 列表
 *  - 移除深色卡/硬阴影/黄色大块（金色只做激励 glyph）
 * 数据口径：【占位·M3】演示帧值；真实可用：问候名 + CTA/会话卡跳转。
 */
import { computed, ref } from 'vue'

import { useAuthStore } from '@/stores/auth'

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

/* ---------- 分段筛选（选中 = 蓝边蓝字加粗） ---------- */
type Tab = 'all' | 'speaking' | 'singing'

const tab = ref<Tab>('all')

const tabs: { key: Tab; label: string; icon: typeof IconChartBar }[] = [
  { key: 'all', label: '全部', icon: IconChartBar },
  { key: 'speaking', label: '口语', icon: IconMicrophone },
  { key: 'singing', label: '唱歌', icon: IconMusic },
]

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
      <!-- 身份：问候 + 头像 -->
      <header class="s-head">
        <div>
          <h1 class="s-h1">{{ greeting() }}，{{ displayName }}</h1>
          <p class="s-caption" style="margin-top: 4px">今天练完这 1 次，就能保住连胜。</p>
        </div>
        <div class="s-avatar" aria-label="头像">{{ avatarLetter }}</div>
      </header>

      <!-- 激励 chip（金色只做 glyph） -->
      <div class="s-streak">
        <IconFlame />
        连续打卡 12 天 · 本周 5/7
      </div>

      <!-- 焦点：今日任务白卡 + 炭黑主按钮（与 Sign In 同款） -->
      <section class="s-plan s-card" aria-label="今日练习">
        <span class="s-plan__badge"><IconFlame style="width: 13px; height: 13px" />今日</span>
        <h2 class="s-plan__title">今日练习</h2>
        <p class="s-plan__sub s-caption">目标 5/7 · 已完成 1 项</p>
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
        <RouterLink to="/m/chat" class="s-btn s-btn--primary s-btn--block">
          <IconMicrophone style="width: 18px; height: 18px" />
          开始今日练习
        </RouterLink>
      </section>

      <!-- 统计白卡（绿=成绩 / 金 glyph=连续） -->
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

      <!-- 筛选：白 pill 按钮组（选中 = 蓝边蓝字，复用表单 .btn hover 语言） -->
      <div class="s-segment" role="tablist" aria-label="练习类型筛选">
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
          <component :is="t.icon" aria-hidden="true" />{{ t.label }}
        </button>
      </div>

      <!-- 轨迹：最近练习（类别色 tint 图标块 + 蓝色数值） -->
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
        <div class="s-empty__icon"><IconMicrophone /></div>
        <div class="s-empty__title">还没有记录</div>
        <div class="s-empty__sub">完成第一次练习后，这里会展示你的成长轨迹。</div>
      </div>

      <p class="s-note" style="margin-top: 20px">
        统计与列表为演示帧数据，M3 接入真实会话记录后自动替换。
      </p>
    </div>

    <MobileTabBar />
  </div>
</template>
