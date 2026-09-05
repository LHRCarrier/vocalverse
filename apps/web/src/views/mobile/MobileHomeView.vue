<script setup lang="ts">
/**
 * 移动端 · 英语社区主页（组长概念拍板 2026-09-05：点赞/分享/评论/投币 · 帖子+视频 · 三个领域）
 *
 * 领域：① 英语新闻稿 ② 英文教学/学习分享 ③ 外国学习生活·地方习俗习惯；视频 = 帖子视频版（排版另设计，参考 X）。
 * 排版参考 X：领域 Tab（推荐=全量）→ 混合信息流（帖子图文卡 / 视频封面卡）→ 互动行（评论/点赞/投币/分享）。
 * 仅数据展示（组长明示）：演示帧数据 + 点赞为本地点赞交互；分享/评论/投币暂为展示。
 * 后端真流 = docs/10 注记（sessions/attempts JOIN 派生 + post_likes）；M3 排期。
 */
import { computed, ref } from 'vue'

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

/* ---------- 领域 Tab（推荐 = 全量混排） ---------- */
type Domain = '新闻稿' | '教学分享' | '海外生活'
const tabs = ['推荐', '新闻稿', '教学分享', '海外生活'] as const
const activeTab = ref<(typeof tabs)[number]>('推荐')

/* ---------- 动态流（【演示帧】仅数据展示；M3 接真实 JOIN 流） ---------- */
interface FeedItem {
  id: number
  author: string
  handle: string
  level: string
  time: string
  domain: Domain
  kind: 'post' | 'video'
  title: string
  desc?: string
  /** 图文帖的配图（演示：渐变块 + 标签）；视频为封面渐变 */
  media?: { gradient: string; label: string }
  duration?: string
  stats: { like: number; comment: number; coin: number; share: number }
  liked: boolean
  tint: string
}

const feed = ref<FeedItem[]>([
  {
    id: 1,
    author: 'Global Post',
    handle: '@globalpost',
    level: 'L4',
    time: '12 分钟前',
    domain: '新闻稿',
    kind: 'post',
    title: "'AI learning' is taking over China's classrooms — what it means for English learners",
    desc: 'Education experts say AI partners are changing how students practice speaking, but human teachers remain the gold standard for feedback.',
    media: { gradient: 'linear-gradient(135deg, #16303a, #2b5566)', label: '📰 NEWS' },
    stats: { like: 328, comment: 46, coin: 37, share: 15 },
    liked: false,
    tint: '#16303a',
  },
  {
    id: 2,
    author: 'BBC Learning English',
    handle: '@bbcle',
    level: 'L3',
    time: '32 分钟前',
    domain: '新闻稿',
    kind: 'video',
    title: '6 Minute English: Why do we procrastinate?',
    desc: 'A new episode with vocabulary that’s actually used in daily conversation.',
    media: { gradient: 'linear-gradient(135deg, #3a2440, #6b3f78)', label: '🎬 VIDEO' },
    duration: '6:23',
    stats: { like: 1240, comment: 189, coin: 210, share: 96 },
    liked: false,
    tint: '#3a2440',
  },
  {
    id: 3,
    author: 'Emma · 英文教学',
    handle: '@emmashare',
    level: 'L3',
    time: '1 小时前',
    domain: '教学分享',
    kind: 'post',
    title: '5 phrasal verbs that make you sound natural at a coffee shop',
    desc: '1) pick up 2) sit down 3) pour out 4) hand over 5) run out of — with example dialogues for each. Save this before your next role-play!',
    media: { gradient: 'linear-gradient(135deg, #1e2b26, #3d5648)', label: '✍️ STUDY' },
    stats: { like: 86, comment: 12, coin: 25, share: 8 },
    liked: false,
    tint: '#1e2b26',
  },
  {
    id: 4,
    author: 'Teacher Lee',
    handle: '@leeenglish',
    level: 'L4',
    time: '2 小时前',
    domain: '教学分享',
    kind: 'video',
    title: 'How I memorize 100 new words a month — the shadowing method',
    desc: 'My 10-minute daily routine: listen, shadow, record, compare. Full breakdown inside.',
    media: { gradient: 'linear-gradient(135deg, #232044, #4a4396)', label: '🎬 VIDEO' },
    duration: '8:12',
    stats: { like: 512, comment: 77, coin: 130, share: 41 },
    liked: false,
    tint: '#232044',
  },
  {
    id: 5,
    author: 'Liz 在伦敦',
    handle: '@lizinlondon',
    level: 'L3',
    time: '3 小时前',
    domain: '海外生活',
    kind: 'post',
    title: 'My first Bonfire Night — why Brits burn effigies on 5th November',
    desc: 'Guy Fawkes Night explained in 3 sentences: a failed plot, a bonfire tradition, and my first "penny for the guy". Tonight we watched sparks over the Thames.',
    stats: { like: 150, comment: 23, coin: 18, share: 12 },
    liked: false,
    tint: '#0f3a44',
  },
  {
    id: 6,
    author: '大米在 Boston',
    handle: '@damilinboston',
    level: 'L2',
    time: '昨天 21:40',
    domain: '海外生活',
    kind: 'video',
    title: 'Dorm life at MIT: my morning in 60 seconds',
    desc: 'Kitchen talk, roommate practices, and the shortest walk to class I could find.',
    media: { gradient: 'linear-gradient(135deg, #2b4a3a, #5c8a6a)', label: '🎬 VIDEO' },
    duration: '1:02',
    stats: { like: 73, comment: 9, coin: 22, share: 5 },
    liked: false,
    tint: '#2b4a3a',
  },
  {
    id: 7,
    author: 'Saki 在京都',
    handle: '@sakiinkyoto',
    level: 'L2',
    time: '昨天 15:06',
    domain: '海外生活',
    kind: 'post',
    title: 'Japanese school lunch culture — 25 minutes of mindful eating',
    desc: 'Students serve each other, eat together, and never waste. The "kyushoku" system teaches more than nutrition — it teaches community.',
    stats: { like: 201, comment: 34, coin: 41, share: 19 },
    liked: false,
    tint: '#4a3320',
  },
  {
    id: 8,
    author: 'Global Post',
    handle: '@globalpost',
    level: 'L4',
    time: '2 天前',
    domain: '新闻稿',
    kind: 'post',
    title: 'Tourism rebound: the quiet villages welcoming slow travellers',
    desc: 'As visa policies ease, small towns across Europe are betting on "slow travel" — longer stays, fewer tourists, richer culture.',
    media: { gradient: 'linear-gradient(135deg, #37546e, #6e96b4)', label: '🗺️ TRAVEL' },
    stats: { like: 468, comment: 55, coin: 63, share: 27 },
    liked: false,
    tint: '#37546e',
  },
])

const visibleFeed = computed(() =>
  activeTab.value === '推荐' ? feed.value : feed.value.filter((f) => f.domain === activeTab.value),
)

function fmt(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

function toggleLike(item: FeedItem) {
  item.liked = !item.liked
  item.stats.like += item.liked ? 1 : -1
}
</script>

<template>
  <div class="u-phone">
    <div class="u-comm">
      <!-- 身份：社区 + 问候 + 头像 -->
      <header class="u-comm__head">
        <div>
          <h1 class="u-comm__title">社区</h1>
          <p class="u-comm__sub">{{ greeting() }}，{{ displayName }} · 英语同好正在分享</p>
        </div>
        <span class="u-comm__avatar" aria-label="头像">{{ avatarLetter }}</span>
      </header>

      <!-- 核心闭环入口（组长护栏：社交不埋训练入口） -->
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

      <!-- 领域 Tab（X 式：推荐 = 全量混排） -->
      <div class="u-comm-tabs" role="tablist" aria-label="社区领域">
        <button
          v-for="t in tabs"
          :key="t"
          class="u-comm-tab"
          :class="{ active: activeTab === t }"
          type="button"
          role="tab"
          :aria-selected="activeTab === t"
          @click="activeTab = t"
        >
          {{ t }}
        </button>
      </div>

      <!-- 信息流：帖子图文卡 / 视频封面卡（参考 X） -->
      <section v-for="item in visibleFeed" :key="item.id" class="u-comm-item" :aria-label="`${item.author} 的动态`">
        <header class="u-comm-item__head">
          <span class="u-comm-item__ava" :style="{ background: item.tint }">{{ item.author.slice(0, 1) }}</span>
          <span class="u-comm-item__who">
            <span class="u-comm-item__name">{{ item.author }} <span class="u-comm-item__domain">{{ item.domain }}</span></span>
            <span class="u-comm-item__meta">{{ item.handle }} · {{ item.level }} · {{ item.time }}</span>
          </span>
        </header>

        <h3 class="u-comm-item__title">{{ item.title }}</h3>
        <p v-if="item.desc" class="u-comm-item__desc">{{ item.desc }}</p>

        <!-- 配图 / 视频封面 -->
        <div
          v-if="item.media"
          class="u-comm-media"
          :class="{ 'u-comm-media--video': item.kind === 'video' }"
          :style="{ background: item.media.gradient }"
        >
          <span v-if="item.kind === 'video'" class="u-comm-media__play"><MobileIcon name="play" :size="22" /></span>
          <span v-if="item.duration" class="u-comm-media__dur">{{ item.duration }}</span>
          <span class="u-comm-media__label">{{ item.media.label }}</span>
        </div>

        <!-- 互动行：评论 / 点赞 / 投币 / 分享（X 式） -->
        <footer class="u-comm-item__foot">
          <span class="u-comm-action">
            <MobileIcon name="chat" :size="15" />
            {{ fmt(item.stats.comment) }}
          </span>
          <button
            class="u-comm-action"
            :class="{ 'is-liked': item.liked }"
            type="button"
            :aria-pressed="item.liked"
            :aria-label="item.liked ? '取消点赞' : '点赞'"
            @click="toggleLike(item)"
          >
            <MobileIcon name="heart" :size="15" />
            {{ fmt(item.stats.like) }}
          </button>
          <span class="u-comm-action">
            <MobileIcon name="coin" :size="15" />
            {{ fmt(item.stats.coin) }}
          </span>
          <span class="u-comm-action">
            <MobileIcon name="share" :size="15" />
            {{ fmt(item.stats.share) }}
          </span>
        </footer>
      </section>

      <p class="u-comm__note">内容为演示数据，仅展示；互动与真实流的接口按 docs/10 注记排期 M3。</p>
    </div>

    <MobileTabBar />
  </div>
</template>
