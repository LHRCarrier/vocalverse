<script setup lang="ts">
/**
 * 移动端 · 英语社区主页（组长概念拍板 2026-09-05：点赞/分享/评论/投币 · 帖子+视频 · 三个领域）
 *
 * 领域：① 英语新闻稿 ② 英文教学/学习分享 ③ 外国学习生活·地方习俗习惯；视频 = 帖子视频版（排版另设计，参考 X）。
 * 排版参考 X：领域 Tab（推荐=全量）→ 混合信息流（帖子图文卡 / 视频封面卡）→ 互动行（评论/点赞/投币/分享）。
 * 仅数据展示（组长明示）：演示帧数据 + 点赞为本地点赞交互；分享/评论/投币暂为展示。
 * 组件拆分（docs/34 §4）：MobilePostCard / MobilePostMedia / MobilePostActions；状态规范见
 * docs/design-system/vocalverse/pages/community.md（加载/空态分支 M3 接真实流后生效）。
 * 后端真流 = docs/10 注记（sessions/attempts JOIN 派生 + post_likes）；M3 排期。
 */
import { computed, ref } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobilePostCard from '@/components/mobile/MobilePostCard.vue'
import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import { COMMUNITY_TABS, DEMO_FEED } from '@/data/community-demo'
import { useAuthStore } from '@/stores/auth'
import '@/styles/mobile-uic.css'

import type { CommunityPost, CommunityTab } from '@/types/community'

const auth = useAuthStore()

const displayName = ref(auth.me?.nickname ?? auth.me?.username ?? '同学')
const avatarLetter = ref(displayName.value.slice(0, 1).toUpperCase())

/* ---------- 领域标签（X 式：为你推荐 = 全量混排） ---------- */
const tabs = COMMUNITY_TABS
const activeTab = ref<CommunityTab>('为你推荐')

/* 加好友演示 toast（仅数据展示 · M3 接真实好友/关注流） */
const toastText = ref('')
let toastTimer: ReturnType<typeof setTimeout> | null = null

function demoAddFriend() {
  toastText.value = '好友请求已发送 · M3 上线'
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toastText.value = ''
  }, 2200)
}

/* ---------- 动态流（【演示帧】仅数据展示；M3 接真实 JOIN 流，只换数据源——docs/34 §7） ---------- */
/** 深拷贝演示数据（点赞会改 item，不能直接引用模块级常量） */
function clonePost(p: CommunityPost): CommunityPost {
  return { ...p, stats: { ...p.stats } }
}

const items = ref<CommunityPost[]>(DEMO_FEED.map(clonePost))
const feedLoading = ref(false)

const visibleFeed = computed(() =>
  activeTab.value === '为你推荐' ? items.value : items.value.filter((f) => f.domain === activeTab.value),
)

function toggleLike(item: CommunityPost) {
  item.liked = !item.liked
  item.stats.like += item.liked ? 1 : -1
}

/** 空态「刷新看看」：演示帧直接重置为演示数据（M3 换真实列表接口 + loading/错误态） */
function reloadFeed() {
  items.value = DEMO_FEED.map(clonePost)
}
</script>

<template>
  <div class="u-phone">
    <div class="u-comm">
      <!-- X 式顶栏（左头像 / 中 Logo / 右加好友；随滚动移出屏幕，非 sticky） -->
      <header class="u-x-top">
        <span class="u-x-avatar" aria-label="头像">{{ avatarLetter }}</span>
        <span class="u-x-logo">社区</span>
        <button class="u-x-act" type="button" title="加好友（演示）" aria-label="加好友" @click="demoAddFriend">
          <MobileIcon name="user-plus" :size="18" />
        </button>
      </header>

      <!-- 领域标签行（X 式文字标签：为你推荐▾ + 三个领域） -->
      <nav class="u-x-tabs" aria-label="社区领域">
        <button
          v-for="t in tabs"
          :key="t"
          class="u-x-tab"
          :class="{ active: activeTab === t }"
          type="button"
          :aria-selected="activeTab === t"
          @click="activeTab = t"
        >
          {{ t }}
          <span v-if="t === '为你推荐'" class="u-x-caret" aria-hidden="true">▾</span>
        </button>
      </nav>

      <!-- 加载态：骨架卡（M3 真实流 >300ms 才出现；docs/31 硬规则 3） -->
      <section v-if="feedLoading" class="u-comm-skel" aria-label="动态加载中" aria-busy="true">
        <div v-for="i in 3" :key="i" class="u-comm-skel__card">
          <span class="u-comm-skel__ava" />
          <span class="u-comm-skel__lines">
            <span class="u-comm-skel__line" style="width: 52%" />
            <span class="u-comm-skel__line" style="width: 78%" />
          </span>
          <span class="u-comm-skel__media" />
        </div>
      </section>

      <!-- 空态：当前领域无内容（M3 出现条件；演示帧各领域均有数据） -->
      <div v-else-if="visibleFeed.length === 0" class="u-comm-empty" role="status">
        <span class="u-comm-empty__icon"><MobileIcon name="info" :size="28" /></span>
        <p class="u-comm-empty__title">该领域暂无内容</p>
        <p class="u-comm-empty__sub">换个领域看看，或稍后再来～</p>
        <button class="u-comm-empty__btn" type="button" @click="reloadFeed">
          <MobileIcon name="refresh" :size="15" />
          刷新看看
        </button>
      </div>

      <!-- 信息流：帖子图文卡 / 视频封面卡（参考 X；组件拆分 docs/34 §4） -->
      <template v-else>
        <MobilePostCard
          v-for="item in visibleFeed"
          :key="item.id"
          :post="item"
          @toggle-like="toggleLike(item)"
        />
      </template>

      <p class="u-comm__note">内容为演示数据，仅展示；互动与真实流的接口按 docs/10 注记排期 M3。</p>
    </div>

    <!-- 发布演示 toast（X 式蓝药丸 → 我们白卡 + 圆点） -->
    <div v-if="toastText" class="u-toast show"><span class="dot" aria-hidden="true" />{{ toastText }}</div>

    <MobileTabBar />
  </div>
</template>
