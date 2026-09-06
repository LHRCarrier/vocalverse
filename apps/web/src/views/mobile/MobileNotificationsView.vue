<script setup lang="ts">
/**
 * 移动端 · 通知中心（2026-09-09 组长反馈：消息收敛到通知——X 式一个入口 tab 分流）
 *
 * S2 真实化（docs/41 · 2026-09-06）：
 * - 「通知」= 互动通知：interactions/评论**派生**（不建表）——like/coin/share 按
 *   (post, action, 当日) mergeKey 聚合为「张三 等 N 人…」（docs/38 §5 模板）；评论逐条带内容；
 * - 「关注」= 我关注的人（管理：推荐关注可关注/取关）+ 关注流（被关注作者最新内容）；
 * - 「私信」= 演示帧保留（IM 范围，S3 后另议），顶部标注不变。
 */
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import IconMail from '~icons/tabler/mail'
import IconSettings from '~icons/tabler/settings'

import {
  fetchFollowingFeed,
  fetchFollowRecommendations,
  fetchFollows,
  fetchNotifications,
  followUser,
  timeAgo,
  unfollowUser,
} from '@/api/community'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { createDemoConversations } from '@/data/messages-demo'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

import type {
  CommunityPostView,
  FollowRecommend,
  FollowSummary,
  NotificationItem,
} from '@/types/community'

const tabs = ['私信', '通知', '关注'] as const
type Tab = (typeof tabs)[number]

const MAPPING: Record<string, Tab> = { msg: '私信', notice: '通知', follow: '关注' }

const route = useRoute()
const activeTab = ref<Tab>('私信')

/* ?tab=msg|notice|follow 直达（抽屉通知下拉子项 · 2026-09-09） */
watch(
  () => route.query.tab,
  (v) => {
    const t = MAPPING[String(v ?? '')]
    if (t) activeTab.value = t
  },
  { immediate: true },
)

const ui = useUiStore()
const conversations = ref(createDemoConversations())

function newMessage() {
  ui.showToast('新消息 · S3 上线')
}
function messageSettings() {
  ui.showToast('通知设置 · S3 上线')
}

/* ---------- S2 · 互动通知（真实派生 + mergeKey 聚合） ---------- */
const notices = ref<NotificationItem[]>([])
const noticesCursor = ref<string | null>(null)
const noticesHasMore = ref(false)
const noticesLoading = ref(false)

const NOTICE_ICON: Record<string, string> = {
  like: 'heart',
  coin: 'star',
  share: 'share',
  comment: 'chat',
}
const NOTICE_ACTION: Record<string, string> = {
  like: '赞了',
  coin: '支持了',
  share: '分享了',
  comment: '评论了',
}

type NoticeIconName = 'heart' | 'star' | 'share' | 'chat'

/** 模板内不支持 TS 断言（`|` 会被当作过滤器语法），类型收窄移入脚本 */
function noticeIconName(type: string): NoticeIconName {
  return (NOTICE_ICON[type] ?? 'heart') as NoticeIconName
}

function noticeWho(n: NotificationItem): string {
  return n.type === 'comment' || n.actorCount <= 1 ? n.actorNickname : `${n.actorNickname} 等 ${n.actorCount} 人`
}

function noticeText(n: NotificationItem): string {
  const head = `你的内容《${n.postTitle}》`
  if (n.type === 'comment') {
    return `${NOTICE_ACTION.comment}${head}：${n.commentBody ?? ''}`
  }
  return `${NOTICE_ACTION[n.type] ?? ''}${head}`
}

async function loadNotices() {
  noticesLoading.value = true
  try {
    const page = await fetchNotifications(null)
    notices.value = page.items
    noticesCursor.value = page.nextCursor
    noticesHasMore.value = page.hasMore
  } catch (e) {
    ui.showToast(e instanceof Error ? e.message : '通知加载失败')
  } finally {
    noticesLoading.value = false
  }
}

async function loadMoreNotices() {
  if (!noticesCursor.value || !noticesHasMore.value) return
  try {
    const page = await fetchNotifications(noticesCursor.value)
    notices.value = notices.value.concat(page.items)
    noticesCursor.value = page.nextCursor
    noticesHasMore.value = page.hasMore
  } catch (e) {
    ui.showToast(e instanceof Error ? e.message : '加载更多失败')
  }
}

/* ---------- S2 · 关注（管理 + 关注流） ---------- */
const followList = ref<FollowSummary[]>([])
const recommendations = ref<FollowRecommend[]>([])
const followingFeed = ref<CommunityPostView[]>([])
const followsLoading = ref(false)

async function loadFollows() {
  followsLoading.value = true
  try {
    const [list, recs, feed] = await Promise.all([fetchFollows(), fetchFollowRecommendations(), fetchFollowingFeed(null, 10)])
    followList.value = list
    recommendations.value = recs
    followingFeed.value = feed.items
  } catch (e) {
    ui.showToast(e instanceof Error ? e.message : '关注加载失败')
  } finally {
    followsLoading.value = false
  }
}

async function toggleFollow(rec: FollowRecommend) {
  try {
    if (rec.followed) {
      await unfollowUser(rec.author.id)
      ui.showToast(`已取消关注 ${rec.author.nickname}`)
    } else {
      await followUser(rec.author.id)
      ui.showToast(`已关注 ${rec.author.nickname}`)
    }
    await loadFollows()
  } catch (e) {
    ui.showToast(e instanceof Error ? e.message : '操作失败')
  }
}

/* Tab 切换懒加载 */
watch(
  activeTab,
  (t) => {
    if (t === '通知') void loadNotices()
    if (t === '关注') void loadFollows()
  },
  { immediate: true },
)

const hasFollows = computed(() => followList.value.length > 0)
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="通知">
      <template #actions>
        <button class="u-topbar__act" type="button" title="新消息（演示）" aria-label="新消息" @click="newMessage">
          <IconMail />
        </button>
        <button class="u-topbar__act" type="button" title="通知设置（演示）" aria-label="通知设置" @click="messageSettings">
          <IconSettings />
        </button>
      </template>
    </MobileTopBar>

    <p class="u-note u-notif__demo">私信为演示数据；通知/关注为真实流（S2）。</p>

    <!-- X 式 tab（均分整行 · 激活加粗 + 下划线） -->
    <nav class="u-notif-tabs" aria-label="通知分类">
      <button
        v-for="t in tabs"
        :key="t"
        class="u-notif-tab"
        :class="{ active: activeTab === t }"
        type="button"
        :aria-selected="activeTab === t"
        @click="activeTab = t"
      >
        {{ t }}
      </button>
    </nav>

    <!-- Tab 1 · 私信（原 /m/messages 列表收敛 · 演示帧） -->
    <div v-if="activeTab === '私信'" class="u-msg">
      <RouterLink
        v-for="c in conversations"
        :key="c.id"
        :to="`/m/messages/${c.id}`"
        class="u-msg__row"
        :aria-label="`与 ${c.name} 的对话`"
      >
        <span class="u-msg__ava" :style="{ background: c.tint }">{{ c.name.slice(0, 1) }}</span>
        <span class="u-msg__body">
          <span class="u-msg__who">
            <strong>{{ c.name }}<span class="u-msg__lv">LV{{ c.level.slice(1) }}</span></strong>
            <time class="u-msg__time">{{ c.time }}</time>
          </span>
          <span class="u-msg__last">{{ c.lastMsg }}</span>
        </span>
        <span v-if="c.unread" class="u-msg__dot" aria-label="未读" />
      </RouterLink>
    </div>

    <!-- Tab 2 · 互动通知（真实派生：类型图标位 + 标题=互动方 + 正文=动作/内容） -->
    <div v-else-if="activeTab === '通知'" class="u-msg">
      <p v-if="noticesLoading" class="u-note u-notif__demo">通知加载中…</p>
      <section v-for="n in notices" :key="n.id" class="u-msg__row">
        <span class="u-msg__ava u-msg__ava--icon">
          <MobileIcon :name="noticeIconName(n.type)" :size="20" />
        </span>
        <span class="u-msg__body">
          <span class="u-msg__who">
            <strong>{{ noticeWho(n) }}</strong>
            <time class="u-msg__time">{{ timeAgo(n.createdAt) }}</time>
          </span>
          <span class="u-msg__last">{{ noticeText(n) }}</span>
        </span>
      </section>
      <p v-if="!noticesLoading && notices.length === 0" class="u-note u-notif__demo" style="text-align: center; margin-top: 20px">
        还没有互动通知——去社区给别人点赞/评论试试。
      </p>
      <button
        v-if="noticesHasMore"
        class="u-comm-more"
        type="button"
        @click="loadMoreNotices"
      >
        加载更多
      </button>
    </div>

    <!-- Tab 3 · 关注（推荐关注管理 + 关注流） -->
    <div v-else class="u-msg">
      <template v-if="!followsLoading">
        <section v-if="recommendations.length" class="u-notif__recs" aria-label="推荐关注">
          <h3 class="u-notif__recs-title">推荐关注</h3>
          <div
            v-for="r in recommendations"
            :key="r.author.id"
            class="u-msg__row u-notif__rec"
          >
            <span class="u-msg__ava" :style="{ background: r.author.tint ?? '#37546e' }">{{
              r.author.nickname.slice(0, 1)
            }}</span>
            <span class="u-msg__body">
              <span class="u-msg__who">
                <strong>{{ r.author.nickname }}</strong>
                <time class="u-msg__time">LV{{ r.author.level.slice(1) }}</time>
              </span>
              <span class="u-msg__last">@{{ r.author.handle }}</span>
            </span>
            <button
              class="u-notif-follow-btn"
              :class="{ active: r.followed }"
              type="button"
              :aria-label="r.followed ? `取消关注 ${r.author.nickname}` : `关注 ${r.author.nickname}`"
              @click="toggleFollow(r)"
            >
              {{ r.followed ? '已关注' : '关注' }}
            </button>
          </div>
        </section>

        <h3 v-if="followingFeed.length" class="u-notif__recs-title">关注动态</h3>
        <section v-for="p in followingFeed" :key="p.id" class="u-msg__row">
          <span class="u-msg__ava" :style="{ background: p.author.tint ?? '#37546e' }">{{
            p.author.nickname.slice(0, 1)
          }}</span>
          <span class="u-msg__body">
            <span class="u-msg__who">
              <strong>{{ p.author.nickname }}</strong>
              <time class="u-msg__time">{{ timeAgo(p.createdAt) }}</time>
            </span>
            <span class="u-msg__last">{{ p.title ?? p.body }} · 👍 {{ p.likeCount }}</span>
          </span>
        </section>
      </template>

      <p
        v-if="!followsLoading && !hasFollows && recommendations.length === 0"
        class="u-note u-notif__demo"
        style="text-align: center; margin-top: 20px"
      >
        还没有关注的人——在上方推荐里点「关注」试试。
      </p>
    </div>
  </div>
</template>
