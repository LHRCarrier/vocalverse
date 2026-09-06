<script setup lang="ts">
/**
 * 移动端 · 英语社区主页（组长概念拍板 2026-09-05：点赞/分享/评论/投币 · 帖子+视频 · 三个领域）
 *
 * S1 真实流（docs/37 §8）：数据源 = Java 社区接口（keyset 游标 + 服务端领域过滤）；
 * 骨架/空态/刷新分支正式启用；打卡卡（kind=checkin）独立卡片（整体分 + 今日次数）。
 * 领域 Tab（X 式）：为你推荐=全量混排（含打卡卡）；三领域=domain 过滤。
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import IconMail from '~icons/tabler/mail'
import IconUserPlus from '~icons/tabler/user-plus'

import { COMMUNITY_TABS } from '@/api/community'
import MobileCommentsSheet from '@/components/mobile/MobileCommentsSheet.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobilePostCard from '@/components/mobile/MobilePostCard.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { shareDemoLink } from '@/composables/share'
import { useCommunityStore } from '@/stores/community'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

import type { CommunityPostView } from '@/types/community'

const router = useRouter()
const ui = useUiStore()
const community = useCommunityStore()

const tabs = COMMUNITY_TABS
const activeTab = ref<string | null>(null)

/* 首页即拉流（真实数据） */
void community.load(null)

watch(activeTab, (id) => {
  void community.load(id)
})

/* 加好友 → 关注管理（S2 真实：跳通知中心「关注」tab，推荐关注里一键关注/取关） */
function demoAddFriend() {
  ui.showToast('关注管理 → 通知中心「关注」')
  void router.push({ path: '/m/notifications', query: { tab: 'follow' } })
}

/* 写消息（X 顶栏同款：私信入口 · 收敛进通知中心；S1 演示，A-12） */
function openMessages() {
  void router.push('/m/notifications')
}

/* ---------- 互动（后端真实接口·乐观更新） ---------- */
const openCommentsId = ref<number | null>(null)
const openCommentsPost = computed(
  () => community.items.find((p) => p.id === openCommentsId.value) ?? null,
)

/** 分享：系统分享面板可用则打开（成功记录一次分享计数）；否则复制演示链接 */
async function sharePost(item: CommunityPostView) {
  const result = await shareDemoLink({
    title: item.title ?? item.body ?? 'VocalVerse 社区内容',
    text: item.body ?? '',
    url: `https://vocalverse.demo/post/${item.id}`,
  })
  if (result === 'shared') {
    await community.share(item)
    ui.showToast('已分享')
  } else if (result === 'copied') ui.showToast('链接已复制（演示链接）')
  else ui.showToast('复制失败，请手动复制')
}

function handleCommentCount(count: number) {
  if (openCommentsId.value != null) community.syncCommentCount(openCommentsId.value, count)
}

/* 底部加载更多（游标） */
function loadMore() {
  void community.loadMore()
}

const visibleFeed = computed(() => community.items)

/** 空态「刷新看看」：真实流重拉 */
function reloadFeed() {
  void community.load(activeTab.value)
}

/** 作者色板取首色（tint #16303a → 渐变双色） */
function tintGradient(tint: string | null | undefined): string {
  if (!tint) return 'linear-gradient(135deg, #37546e, #6e96b4)'
  return `linear-gradient(135deg, ${tint}, #fff3)`
}
</script>

<template>
  <div class="u-phone">
    <!-- 统一顶栏（全局头像 → 账户抽屉 / 标题「社区」/ 右侧：加好友 + 写消息） -->
    <MobileTopBar title="社区">
      <template #actions>
        <button class="u-topbar__act" type="button" title="关注" aria-label="关注" @click="demoAddFriend">
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
          :key="t.label"
          class="u-x-tab"
          :class="{ active: activeTab === t.id }"
          type="button"
          :aria-selected="activeTab === t.id"
          @click="activeTab = t.id"
        >
          {{ t.label }}
          <span v-if="t.id === null" class="u-x-caret" aria-hidden="true">▾</span>
        </button>
      </nav>

      <!-- 加载态：骨架卡（docs/31 硬规则 3：>300ms 才出现） -->
      <section v-if="community.loading" class="u-comm-skel" aria-label="动态加载中" aria-busy="true">
        <div v-for="i in 3" :key="i" class="u-comm-skel__card">
          <span class="u-comm-skel__ava" />
          <span class="u-comm-skel__lines">
            <span class="u-comm-skel__line" style="width: 52%" />
            <span class="u-comm-skel__line" style="width: 78%" />
          </span>
          <span class="u-comm-skel__media" />
        </div>
      </section>

      <!-- 空态：当前领域无内容 -->
      <div v-else-if="visibleFeed.length === 0" class="u-comm-empty" role="status">
        <span class="u-comm-empty__icon"><MobileIcon name="info" :size="28" /></span>
        <p class="u-comm-empty__title">{{ community.error ? '加载失败' : '该领域暂无内容' }}</p>
        <p class="u-comm-empty__sub">{{ community.error || '换个领域看看，或稍后再来～' }}</p>
        <button class="u-comm-empty__btn" type="button" @click="reloadFeed">
          <MobileIcon name="refresh" :size="15" />
          刷新看看
        </button>
      </div>

      <!-- 信息流：帖子图文卡 / 视频封面卡 / 打卡卡（参考 X；组件拆分 docs/34 §4） -->
      <template v-else>
        <MobilePostCard
          v-for="item in visibleFeed"
          :key="item.id"
          :post="item"
          :tint-gradient="tintGradient(item.author.tint)"
          @toggle-like="community.toggleLike(item)"
          @coin="community.coin(item)"
          @share="sharePost(item)"
          @open-comments="openCommentsId = item.id"
        />
      </template>

      <!-- 游标加载更多 -->
      <button
        v-if="community.hasMore && !community.loading"
        class="u-comm-more"
        type="button"
        :disabled="community.loadingMore"
        @click="loadMore"
      >
        {{ community.loadingMore ? '加载中…' : '加载更多' }}
      </button>

      <p class="u-comm__note">内容为社区真实数据：三领域 Tab 服务端过滤；为你推荐=全量混排（含打卡卡）。</p>
    </div>

    <!-- 评论面板（真实流：服务端列表 + 发表；嵌套楼 S3；v-if 守卫下的可选链兜底） -->
    <MobileCommentsSheet
      v-if="openCommentsPost"
      :post-id="openCommentsPost?.id ?? 0"
      :open="openCommentsId !== null"
      :title="openCommentsPost?.title ?? openCommentsPost?.body ?? '内容'"
      :comment-count="openCommentsPost?.commentCount ?? 0"
      @update:open="openCommentsId = null"
      @update-count="handleCommentCount"
    />
  </div>
</template>
