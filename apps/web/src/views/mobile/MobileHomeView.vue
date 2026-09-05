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
import { useRouter } from 'vue-router'

import IconMail from '~icons/tabler/mail'
import IconUserPlus from '~icons/tabler/user-plus'

import MobileCommentsSheet from '@/components/mobile/MobileCommentsSheet.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobilePostCard from '@/components/mobile/MobilePostCard.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { shareDemoLink } from '@/composables/share'
import { COMMUNITY_TABS, DEMO_FEED } from '@/data/community-demo'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

import type { CommunityPost, CommunityTab } from '@/types/community'

const auth = useAuthStore()
const router = useRouter()
const ui = useUiStore()

/* ---------- 领域标签（X 式：为你推荐 = 全量混排） ---------- */
const tabs = COMMUNITY_TABS
const activeTab = ref<CommunityTab>('为你推荐')

/* 加好友演示（仅数据展示 · M3 接真实好友/关注流） */
function demoAddFriend() {
  ui.showToast('好友请求已发送 · M3 上线')
}

/* 写消息（X 顶栏同款：私信入口） */
function openMessages() {
  void router.push('/m/messages')
}

/* ---------- 互动（组长 2026-09-05 升级拍板：评论/投币/分享全交互 · 演示帧本地，不落库） ---------- */
const openCommentsId = ref<number | null>(null)
const openCommentsPost = computed(() => items.value.find((p) => p.id === openCommentsId.value) ?? null)

function toggleCoin(item: CommunityPost) {
  item.coined = !item.coined
  item.stats.coin += item.coined ? 1 : -1
}

/** 分享：系统分享面板可用则打开；否则复制演示链接（分享计数=转发数语义，点击不加计） */
async function sharePost(item: CommunityPost) {
  const result = await shareDemoLink({
    title: item.title,
    text: item.desc ?? '',
    url: `https://vocalverse.demo/post/${item.id}`,
  })
  if (result === 'shared') ui.showToast('已分享')
  else if (result === 'copied') ui.showToast('链接已复制（演示链接）')
  else if (result === 'failed') ui.showToast('复制失败，请手动复制')
}

function addComment(item: CommunityPost, text: string) {
  const author = auth.me?.nickname ?? auth.me?.username ?? '你'
  item.comments.push({ author, text, time: '刚刚' })
  item.stats.comment += 1
}

function handleAddComment(text: string) {
  if (openCommentsPost.value) addComment(openCommentsPost.value, text)
}

/* ---------- 动态流（【演示帧】仅数据展示；M3 接真实 JOIN 流，只换数据源——docs/34 §7） ---------- */
/** 深拷贝演示数据（点赞/投币/评论会改 item，不能直接引用模块级常量） */
function clonePost(p: CommunityPost): CommunityPost {
  return { ...p, stats: { ...p.stats }, comments: p.comments.slice() }
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
    <!-- 统一顶栏（全局头像 → 账户抽屉 / 标题「社区」/ 右侧：加好友 + 写消息） -->
    <MobileTopBar title="社区">
      <template #actions>
        <button class="u-topbar__act" type="button" title="加好友（演示）" aria-label="加好友" @click="demoAddFriend">
          <IconUserPlus />
        </button>
        <button class="u-topbar__act" type="button" title="写消息" aria-label="写消息" @click="openMessages">
          <IconMail />
        </button>
      </template>
    </MobileTopBar>

    <div class="u-comm">
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
          @toggle-coin="toggleCoin(item)"
          @share="sharePost(item)"
          @open-comments="openCommentsId = item.id"
        />
      </template>

      <p class="u-comm__note">内容为演示数据，仅展示；互动与真实流的接口按 docs/10 注记排期 M3。</p>
    </div>

    <!-- 评论面板（演示级：列表 + 发表；嵌套楼 M3） -->
    <MobileCommentsSheet
      :open="openCommentsId !== null"
      :title="openCommentsPost?.title ?? ''"
      :comments="openCommentsPost?.comments ?? []"
      @update:open="openCommentsId = null"
      @add-comment="handleAddComment"
    />
  </div>
</template>
