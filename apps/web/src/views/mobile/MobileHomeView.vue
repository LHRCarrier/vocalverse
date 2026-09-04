<script setup lang="ts">
/**
 * 移动端首页（UI 先行 · 逐项对齐原型源码 examples/app/home.html）
 * 本页当前为「原型演示帧」：结构/图标/配色/文案与原型源码一致（数据字段打上【占位】注释，
 * M3 埋点聚合/真实会话接入后按「先 UI 后功能」原则替换，不破坏视觉）。
 * 唯一动态项：问候名（真实账户），其余均为原型演示值。
 */
import { computed } from 'vue'

import { useAuthStore } from '@/stores/auth'
import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import '@/styles/mobile-uic.css'

const auth = useAuthStore()

function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

/** 问候名（原型为 "LHR"：真实账户首字/登录名） */
const displayName = computed(() => auth.me?.nickname ?? auth.me?.username ?? 'LHR')

/** 头像字（原型 "L"） */
const avatarLetter = computed(() => displayName.value.slice(0, 1).toUpperCase())

/* ---------- 原型演示帧（home.html 逐项复制；接入后替换） ---------- */
// 【占位·M3】今日会话：原型示例 3 条（真实数据接入后替换；值位 = accent 分数，原型口径）
const sessions = [
  {
    title: 'Coffee Shop',
    sub: 'Today 9:30 · 8 rounds · 3m12s',
    value: '86.4',
    color: '#3A2440',
    icon: 'coffee',
  },
  {
    title: 'Perfect Night',
    sub: 'Yesterday · 2 takes · pitch 88',
    value: '88.1',
    color: '#232044',
    icon: 'music',
  },
  {
    title: 'Job Interview',
    sub: 'Sep 12 · 6 rounds',
    value: '79.8',
    color: '#16303A',
    icon: 'briefcase',
  },
] as const
// 【占位·M3】统计卡：Rounds 38 / Avg score 86.4 / Goal 5/7（原型演示值）
// 【占位·M3】打卡：Streak 12 days（原型演示值）
</script>

<template>
  <div class="u-phone">
    <div class="u-content">
      <!-- 问候 + 头像（原型 home.html .head） -->
      <header class="u-head">
        <div>
          <h1>{{ greeting() }}, {{ displayName }}</h1>
          <p>One scene today keeps your 7-day streak.</p>
        </div>
        <div class="u-avatar">{{ avatarLetter }}</div>
      </header>

      <!-- 打卡徽章（原型 .streak） -->
      <div class="u-streak">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M12 3.5c1 2.5 4.5 4 4.5 8.5a4.5 4.5 0 0 1-9 0c0-1.8.8-3 1.7-4.2.4 1 .9 1.6 1.8 2.2-.3-2.2.2-4.6 1-6.5z" />
        </svg>
        Streak 12 days
      </div>

      <!-- 统计卡（原型 .stats） -->
      <section class="u-stats">
        <div><div class="u-stat-label">Rounds</div><div class="u-stat-value">38</div></div>
        <div><div class="u-stat-label">Avg score</div><div class="u-stat-value accent">86.4</div></div>
        <div><div class="u-stat-label">Goal</div><div class="u-stat-value">5/7</div></div>
      </section>

      <!-- 分段控件（原型 .segment） -->
      <div class="u-segment">
        <button type="button" class="active">All</button>
        <button type="button">Speaking</button>
        <button type="button">Singing</button>
      </div>

      <!-- 今日会话（原型 .task + 点线时间轴；演示帧数据） -->
      <div class="u-section-title">Today's sessions</div>
      <template v-for="(s, i) in sessions" :key="s.title">
        <div class="u-task" style="cursor: default">
          <span class="u-icon-block" :style="{ background: s.color }">
            <svg v-if="s.icon === 'coffee'" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M5 9h11v5a5 5 0 0 1-5 5H10a5 5 0 0 1-5-5z" /><path d="M16 10h1.5a2.5 2.5 0 0 1 0 5H16" />
            </svg>
            <svg v-else-if="s.icon === 'music'" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M9 18V6l10-2v12" /><circle cx="6.5" cy="18" r="2.5" /><circle cx="16.5" cy="16" r="2.5" />
            </svg>
            <svg v-else viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <rect x="4" y="8" width="16" height="12" rx="3" /><path d="M9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
            </svg>
          </span>
          <span class="u-task-main">
            <span class="u-task-title">{{ s.title }}</span>
            <span class="u-task-sub">{{ s.sub }}</span>
          </span>
          <span class="u-task-value">{{ s.value }}</span>
        </div>
        <div v-if="i < sessions.length - 1" class="u-dotline">
          <span class="dot" /><span class="line" />
        </div>
      </template>
    </div>

    <MobileTabBar />
  </div>
</template>
