<script setup lang="ts">
/**
 * 移动端 · 今日学习（首页）——ui-concept-design skill 重制版
 * 视觉正本：ref-landing-hero-light（线稿锚点 + 信任）/ ref-profile-card-stats（Stat 32px+）
 *          + ref-segmented-pill（分段 56px）+ ref-card-light-timeline（实色图标块 + 点线时间轴）
 * 布局：问候头部 → 打卡徽章 → 今日任务卡（线稿日历锚点 + 主 CTA）→ 统计卡 → 56px 分段
 *      → 最近练习点线时间轴；底部浮动 Tab 栏。
 * 数据口径：【占位·M3】统计/打卡/会话列表为演示帧值，M3 埋点聚合后接入替换（不破坏视觉）。
 * 真实可用：问候名（账户）、「开始今日练习」→ /m/chat（真会话）、会话卡点击跳转。
 */
import { computed, ref } from 'vue'

import { useAuthStore } from '@/stores/auth'

import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import '@/styles/mobile-uic.css'

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

/* ---------- 分段筛选 ---------- */
type Tab = 'all' | 'speaking' | 'singing'

const tab = ref<Tab>('all')

const tabs: { key: Tab; label: string; icon: 'chart' | 'mic' | 'note' }[] = [
  { key: 'all', label: '全部', icon: 'chart' },
  { key: 'speaking', label: '口语', icon: 'mic' },
  { key: 'singing', label: '唱歌', icon: 'note' },
]

/* ---------- 最近练习（【占位·M3】演示帧数据，接入后替换） ---------- */
interface Session {
  id: number
  kind: 'speaking' | 'singing'
  icon: 'coffee' | 'note' | 'briefcase' | 'headphone'
  color: string
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
    icon: 'coffee',
    color: '#3A2440',
    title: '情景对话 · 咖啡店点单',
    sub: '今天 9:30 · 8 轮 · 用时 3 分 12 秒',
    value: '86.4',
    badge: { text: '完成', variant: 'success' },
  },
  {
    id: 2,
    kind: 'singing',
    icon: 'note',
    color: '#232044',
    title: '跟唱 · Perfect Night',
    sub: '昨天 20:15 · 跟唱 2 遍 · 音准 88',
    value: '88.1',
    badge: { text: '新纪录', variant: 'star' },
  },
  {
    id: 3,
    kind: 'speaking',
    icon: 'briefcase',
    color: '#16303A',
    title: '情景对话 · 面试自我介绍',
    sub: '9 月 12 日 · 6 轮 · 中级难度',
    value: '79.8',
    valueInk: true,
    badge: { text: '待提升', variant: 'neutral' },
  },
  {
    id: 4,
    kind: 'singing',
    icon: 'headphone',
    color: '#1E2B26',
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
  <div class="u-phone">
    <div class="u-content">
      <!-- 问候 + 头像（真实账户名） -->
      <header class="u-head">
        <div>
          <h1>{{ greeting() }}，{{ displayName }}</h1>
          <p class="u-head__sub">今天练完这 1 次，就能保住连胜。</p>
        </div>
        <div class="u-avatar">{{ avatarLetter }}</div>
      </header>

      <!-- 打卡徽章 -->
      <div class="u-streak">
        <MobileIcon name="flame" />
        连续打卡 12 天 · 本周 5/7
      </div>

      <!-- 今日任务卡：线稿日历锚点 + 步骤 + 主 CTA -->
      <section class="u-plan">
        <div class="u-plan__art" aria-hidden="true">
          <MobileArt name="calendar" :size="96" />
        </div>
        <div class="u-plan__body">
          <div class="u-plan__title">今日练习</div>
          <div class="u-plan__sub">目标 5/7 · 已完成 1 项</div>
          <div class="u-plan__steps">
            <template v-for="(s, i) in planSteps" :key="i">
              <div v-if="i > 0" class="u-plan__step-line" aria-hidden="true" />
              <div class="u-plan__step">
                <span class="dot" :style="s.done ? { background: 'var(--u-success)' } : undefined" />
                <span :style="s.done ? { color: 'var(--u-weak)', textDecoration: 'line-through' } : undefined">
                  {{ s.text }}
                </span>
                <MobileIcon v-if="s.done" name="check" :size="14" style="color: var(--u-success)" />
              </div>
            </template>
          </div>
          <RouterLink to="/m/chat" class="u-btn u-btn--primary u-btn--block u-plan__cta">
            <MobileIcon name="mic" :size="18" />
            开始今日练习
          </RouterLink>
        </div>
      </section>

      <!-- 统计卡：Caption weak 在上 + Stat 32px 在下 -->
      <section class="u-stats">
        <div>
          <div class="u-stat-label">累计轮数</div>
          <div class="u-stat-value">38</div>
        </div>
        <div>
          <div class="u-stat-label">平均分</div>
          <div class="u-stat-value u-stat-value--accent">86.4</div>
        </div>
        <div>
          <div class="u-stat-label">连续天数</div>
          <div class="u-stat-value u-stat-value--star">
            <MobileIcon name="star" :size="22" />12
          </div>
        </div>
      </section>

      <!-- 全宽分段控件（高 56px，白胶囊浮起） -->
      <div class="u-segment" role="tablist">
        <button
          v-for="t in tabs"
          :key="t.key"
          type="button"
          role="tab"
          :aria-selected="tab === t.key"
          :class="{ active: tab === t.key }"
          @click="tab = t.key"
        >
          <MobileIcon :name="t.icon" />{{ t.label }}
        </button>
      </div>

      <!-- 最近练习：点线时间轴（图标块搁在点线上） -->
      <div class="u-section-title">最近练习</div>
      <template v-for="(s, i) in visibleSessions" :key="s.id">
        <RouterLink
          :to="s.kind === 'speaking' ? '/m/chat' : '/m/sing'"
          class="u-item"
          :aria-label="`查看 ${s.sub}`"
        >
          <span class="u-icon-block" :style="{ background: s.color }">
            <MobileIcon :name="s.icon" :size="22" />
          </span>
          <span class="u-item__main">
            <span class="u-item__title">{{ s.title }}</span>
            <span class="u-item__sub">{{ s.sub }}</span>
          </span>
          <span class="u-item__right">
            <span class="u-item__value" :class="{ 'u-item__value--ink': s.valueInk }">{{ s.value }}</span>
            <span class="u-badge" :class="`u-badge--${s.badge.variant}`">{{ s.badge.text }}</span>
          </span>
        </RouterLink>
        <div v-if="i < visibleSessions.length - 1" class="u-dotline" aria-hidden="true">
          <span class="dot" /><span class="line" />
        </div>
      </template>
      <div v-if="!visibleSessions.length" class="u-empty">
        <div class="u-empty__art"><MobileArt name="mic" :size="96" /></div>
        <div class="u-empty__title">还没有记录</div>
        <div class="u-empty__sub">完成第一次练习后，这里会按时间轴展示你的成长轨迹。</div>
      </div>

      <p class="u-note" style="margin-top: 24px">
        统计与列表为演示帧数据，M3 接入真实会话记录后自动替换。
      </p>
    </div>

    <MobileTabBar />
  </div>
</template>
