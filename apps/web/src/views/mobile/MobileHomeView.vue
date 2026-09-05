<script setup lang="ts">
/**
 * 移动端 · 社区主页（组长拍板 2026-09-05：主页换成社区；原「今日学习」演示帧撤下，列表不杂了）
 *
 * 结构：问候头 + 「今日练习」CTA（核心闭环入口，不被社交淹没）+ 打卡动态流。
 * 数据：演示帧——后端动态流按 docs/10 注记（单日打卡由 sessions 按日派生、跨用户流由
 * sessions/attempts/users JOIN 派生，无新表；M3 排期接真实接口）；点赞为本地交互演示不落库。
 * 设计语言：uic 纸面 + 白卡 24 圆角 + 炭黑主钮 + 点格底（与口语页同源）。
 */
import { ref } from 'vue'

import { useAuthStore } from '@/stores/auth'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import '@/styles/mobile-uic.css'

const auth = useAuthStore()

function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
}

const displayName = ref(auth.me?.nickname ?? auth.me?.username ?? '同学')
const avatarLetter = ref(displayName.value.slice(0, 1).toUpperCase())

/* ---------- 打卡动态流（【演示帧·M3】接真实接口后替换） ---------- */
interface FeedItem {
  id: number
  name: string
  level: string
  time: string
  kind: '场景对话' | '跟唱' | '自由对话'
  title: string
  score: number | null
  badge: { text: string; variant: 'success' | 'star' | 'neutral' }
  meta: string
  like: number
  liked: boolean
  comments: number
  tint: string
}

const feed = ref<FeedItem[]>([
  {
    id: 1,
    name: 'Luna',
    level: 'L3',
    time: '3 分钟前',
    kind: '场景对话',
    title: '咖啡馆 · 点单（进阶）',
    score: 86.4,
    badge: { text: '完成', variant: 'success' },
    meta: '8 轮 · 用时 3′12″ · 三维评分',
    like: 23,
    liked: false,
    comments: 4,
    tint: '#16303a',
  },
  {
    id: 2,
    name: '大树',
    level: 'L3',
    time: '28 分钟前',
    kind: '跟唱',
    title: 'Perfect Night',
    score: 88.1,
    badge: { text: '新纪录', variant: 'star' },
    meta: '跟唱 2 遍 · 音准 88',
    like: 41,
    liked: false,
    comments: 9,
    tint: '#3a2440',
  },
  {
    id: 3,
    name: 'Momo',
    level: 'L2',
    time: '1 小时前',
    kind: '自由对话',
    title: '和 Sam 聊周末计划',
    score: null,
    badge: { text: '打卡', variant: 'neutral' },
    meta: '12 轮 · 自由聊 4′05″',
    like: 8,
    liked: false,
    comments: 1,
    tint: '#1e2b26',
  },
  {
    id: 4,
    name: 'Panda',
    level: 'L1',
    time: '3 小时前',
    kind: '场景对话',
    title: '机场 · 值机出行（入门）',
    score: 79.8,
    badge: { text: '待提升', variant: 'neutral' },
    meta: '6 轮 · 语言点 3/5',
    like: 12,
    liked: false,
    comments: 2,
    tint: '#232044',
  },
  {
    id: 5,
    name: '叽里呱啦',
    level: 'L4',
    time: '昨天 20:15',
    kind: '跟唱',
    title: 'Yesterday Once More',
    score: 91.5,
    badge: { text: '优秀', variant: 'success' },
    meta: '跟唱 1 遍 · 节奏 91',
    like: 66,
    liked: false,
    comments: 15,
    tint: '#16303a',
  },
])

function toggleLike(item: FeedItem) {
  item.liked = !item.liked
  item.like += item.liked ? 1 : -1
}
</script>

<template>
  <div class="u-phone">
    <div class="u-comm">
      <!-- 身份：问候 + 头像 -->
      <header class="u-comm__head">
        <div>
          <h1 class="u-comm__title">社区</h1>
          <p class="u-comm__sub">{{ greeting() }}，{{ displayName }}</p>
        </div>
        <span class="u-comm__avatar" aria-label="头像">{{ avatarLetter }}</span>
      </header>

      <!-- 核心闭环入口：今日练习（组长拍板：社区页保留醒目练习入口，防被社交淹没） -->
      <section class="u-comm__cta" aria-label="今日练习">
        <div class="u-comm__cta-body">
          <h2 class="u-comm__cta-title">今日练习</h2>
          <p class="u-comm__cta-sub">连续打卡 12 天 · 练完再领 1 次连胜</p>
        </div>
        <RouterLink to="/m/chat" class="u-comm__cta-btn">
          <MobileIcon name="mic" :size="16" />
          开始练习
        </RouterLink>
      </section>

      <!-- 打卡动态流 -->
      <h2 class="u-comm__sec">大家今天</h2>
      <section v-for="item in feed" :key="item.id" class="u-comm-item" :aria-label="`${item.name} 的动态`">
        <header class="u-comm-item__head">
          <span class="u-comm-item__ava" :style="{ background: item.tint }">{{ item.name.slice(0, 1) }}</span>
          <span class="u-comm-item__who">
            <span class="u-comm-item__name">{{ item.name }}</span>
            <span class="u-comm-item__meta">{{ item.level }} · {{ item.time }}</span>
          </span>
        </header>
        <div class="u-comm-item__body">
          <span class="u-comm-item__kind">{{ item.kind }}</span>
          <span class="u-comm-item__title">{{ item.title }}</span>
          <span class="u-comm-item__score">
            <template v-if="item.score != null">{{ item.score }}</template>
            <template v-else>—</template>
          </span>
        </div>
        <p class="u-comm-item__meta-line">
          {{ item.meta }}
          <span class="u-chip u-chip--green" :class="`u-comm-badge--${item.badge.variant}`">{{ item.badge.text }}</span>
        </p>
        <footer class="u-comm-item__foot">
          <button
            class="u-comm-item__act"
            :class="{ 'is-liked': item.liked }"
            type="button"
            :aria-pressed="item.liked"
            :aria-label="item.liked ? '取消点赞' : '点赞'"
            @click="toggleLike(item)"
          >
            <MobileIcon name="heart" :size="15" />
            {{ item.like }}
          </button>
          <span class="u-comm-item__act">
            <MobileIcon name="chart" :size="15" />
            {{ item.comments }}
          </span>
        </footer>
      </section>

      <p class="u-comm__note">动态为演示数据，M3 接入真实打卡流（docs/10 注记：sessions/attempts 派生）。</p>
    </div>

    <MobileTabBar />
  </div>
</template>
