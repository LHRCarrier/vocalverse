<script setup lang="ts">
/**
 * 移动端 · 帖子详情（社区 S3 · docs/47 §5.1 · /m/post/:postId）
 *
 * 沉浸页（无底部 TabBar，docs/35 登记第二例外）：
 * 作者行（真实头像）+ 标题/正文（**划词查义**）+ 媒体（宫格/灯箱/视频）+ 互动 + 评论 + 删自己的帖。
 *
 * 拆分纪律（fe-08：max-lines 350）：数据流在 usePostDetail / usePostComments /
 * useCommunityWordLookup，本页只做模板与交互编排。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import MobileAvatar from '@/components/mobile/MobileAvatar.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileMediaGrid from '@/components/mobile/MobileMediaGrid.vue'
import MobileMediaLightbox from '@/components/mobile/MobileMediaLightbox.vue'
import MobilePostActions from '@/components/mobile/MobilePostActions.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import MobileVideoPlayer from '@/components/mobile/MobileVideoPlayer.vue'
import MobileWordCard from '@/components/mobile/MobileWordCard.vue'
import { authorDisplay, domainLabel, timeAgo } from '@/api/community'
import { useBackLayers } from '@/composables/useBackLayers'
import { useCommunityWordLookup } from '@/composables/useCommunityWordLookup'
import { useMobileBack } from '@/composables/useMobileBack'
import { usePostComments } from '@/composables/usePostComments'
import { usePostDetail } from '@/composables/usePostDetail'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { normalizeMedia } from '@/types/community'
import '@/styles/mobile-uic.css'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const auth = useAuthStore()

const postId = Number(route.params.postId)
const goBack = useMobileBack('/m/home')

const { post, loading, error, notFound, deleting, load, toggleLike, coin, share, remove } =
  usePostDetail(postId)
const {
  list: commentList,
  hasMore: commentHasMore,
  loading: commentLoading,
  loadingMore: commentLoadingMore,
  draft: commentDraft,
  submitting: commentSubmitting,
  total: commentTotal,
  load: loadComments,
  loadMore: loadMoreComments,
  submit: submitComment,
} = usePostComments(postId, () => post.value?.commentCount ?? 0)

const word = useCommunityWordLookup()

const media = computed(() => normalizeMedia(post.value?.media, post.value?.kind))
const tintGradient = computed(
  () => `linear-gradient(135deg, ${post.value?.author.tint ?? '#37546e'}, #fff3)`,
)
/** 自己的帖才给删除入口（后端仍会二次校验，见 CommunityService.delete） */
const isMine = computed(() => !!post.value && auth.me?.userId === post.value.author.id)

/* ---------- 媒体灯箱 / 视频播放 ---------- */
const lightboxOpen = ref(false)
const lightboxIndex = ref(0)
const videoOpen = ref(false)

function openLightbox(i: number) {
  lightboxIndex.value = i
  lightboxOpen.value = true
}

async function removePost() {
  if (await remove()) void router.replace('/m/home')
}

/* ---------- 划词（长按选中 → 词卡） ---------- */
const contentEl = ref<HTMLElement | null>(null)
function onSelectionChange() {
  word.onSelectionChange(contentEl.value)
}

onMounted(() => {
  void load().then(() => {
    void loadComments()
  })
  document.addEventListener('selectionchange', onSelectionChange)
})
onBeforeUnmount(() => document.removeEventListener('selectionchange', onSelectionChange))

/* 安卓返回：按层级关闭（否则滑动返回直接退页，docs/48 B14） */
useBackLayers([
  { open: () => lightboxOpen.value, close: () => (lightboxOpen.value = false) },
  { open: () => videoOpen.value, close: () => (videoOpen.value = false) },
  { open: () => word.state.open, close: () => word.close() },
])
</script>

<template>
  <div class="u-phone u-pd">
    <MobileTopBar :title="post?.title ?? '内容'" back @back="goBack">
      <template #actions>
        <button
          v-if="isMine"
          class="u-topbar__act"
          type="button"
          :disabled="deleting"
          title="删除"
          aria-label="删除这条内容"
          @click="removePost"
        >
          <MobileIcon name="trash" :size="18" />
        </button>
      </template>
    </MobileTopBar>

    <main v-if="loading" class="u-pd__body">
      <p class="u-comm-empty__sub">加载中…</p>
    </main>

    <main v-else-if="error" class="u-pd__body">
      <div class="u-comm-empty" role="status">
        <span class="u-comm-empty__icon"><MobileIcon name="info" :size="28" /></span>
        <p class="u-comm-empty__title">{{ notFound ? '内容不存在或已删除' : '加载失败' }}</p>
        <p class="u-comm-empty__sub">{{ error }}</p>
        <button class="u-comm-empty__btn" type="button" @click="notFound ? goBack() : load()">
          {{ notFound ? '返回社区' : '重试' }}
        </button>
      </div>
    </main>

    <main v-else-if="post" ref="contentEl" class="u-pd__body">
      <!-- 作者行 -->
      <header class="u-pd__head">
        <MobileAvatar
          :src="post.author.avatarUrl"
          :name="post.author.nickname"
          :tint="post.author.tint"
          size="md"
        />
        <span class="u-pd__who">
          <span class="u-pd__name">
            {{ post.author.nickname }}
            <span class="u-comm-item__domain">{{ domainLabel(post.domain) }}</span>
          </span>
          <span class="u-comm-item__meta">
            {{ authorDisplay(post.author.handle) }} · LV{{ post.author.level.slice(1) }} ·
            {{ timeAgo(post.createdAt) }}
          </span>
        </span>
      </header>

      <!-- 正文（data-sentence：划词取上下文句） -->
      <h1 v-if="post.title" class="u-pd__title" data-sentence>{{ post.title }}</h1>
      <p v-if="post.body" class="u-pd__text" data-sentence>{{ post.body }}</p>

      <!-- 媒体 -->
      <MobileVideoPlayer
        v-if="media.kind === 'video' && media.items.length"
        class="u-pd__video"
        :url="media.items[0].url"
        :poster="media.coverUrl"
        :tint-gradient="tintGradient"
      />
      <MobileMediaGrid
        v-else
        :media="media"
        :tint-gradient="tintGradient"
        @open="openLightbox"
        @play="videoOpen = true"
      />

      <MobilePostActions
        :like-count="post.likeCount"
        :comment-count="commentTotal()"
        :coin-count="post.coinCount"
        :share-count="post.shareCount"
        :liked="post.liked"
        :coined="post.coined"
        @toggle-like="toggleLike"
        @coin="coin"
        @share="share"
        @open-comments="ui.showToast('评论在下方')"
      />

      <!-- 评论区（内联；与弹层共用 usePostComments） -->
      <section class="u-pd__comments" aria-label="评论">
        <h2 class="u-pd__section-title">评论 · {{ commentTotal() }}</h2>
        <p v-if="commentLoading" class="u-comm-empty__sub">评论加载中…</p>
        <ul v-else-if="commentList.length" class="u-comments__list">
          <li v-for="c in commentList" :key="c.id" class="u-comments__item">
            <MobileAvatar :src="c.author.avatarUrl" :name="c.author.nickname" :tint="c.author.tint" size="sm" />
            <span class="u-comments__body">
              <span class="u-comments__who">
                {{ c.author.nickname }}
                <time class="u-comments__time">{{ timeAgo(c.createdAt) }}</time>
              </span>
              <span class="u-comments__text" data-sentence>{{ c.body }}</span>
            </span>
          </li>
          <li v-if="commentHasMore" class="u-comments__more">
            <button type="button" :disabled="commentLoadingMore" @click="loadMoreComments()">
              加载更多评论
            </button>
          </li>
        </ul>
        <p v-else class="u-comm-empty__sub">还没有评论，来抢沙发～</p>
      </section>
    </main>

    <!-- 评论输入（固定底栏；沉浸页无 TabBar） -->
    <footer v-if="post" class="u-pd__bar">
      <input
        v-model="commentDraft"
        class="u-comments__input"
        type="text"
        maxlength="500"
        placeholder="写下你的评论…"
        aria-label="评论内容"
        @keydown.enter="submitComment()"
      >
      <button
        class="u-comments__send"
        type="button"
        :disabled="!commentDraft.trim() || commentSubmitting"
        aria-label="发表评论"
        @click="submitComment()"
      >
        <MobileIcon name="arrow" :size="16" />
      </button>
    </footer>

    <MobileMediaLightbox
      :open="lightboxOpen"
      :items="media.items"
      :index="lightboxIndex"
      @update:open="lightboxOpen = $event"
      @update:index="lightboxIndex = $event"
    />

    <!-- 划词词卡（复用读书域组件；社区只提供 scene=community 的入库来源） -->
    <MobileWordCard
      v-if="word.state.open"
      :result="word.state.result"
      :loading="word.state.loading"
      :missing="word.state.missing"
      :sentence-index="null"
      @close="word.close()"
      @add-vocab="word.addToVocab()"
      @play-word="word.playWord()"
      @sentence-highlight="ui.showToast('社区内容不支持批注')"
      @sentence-note="ui.showToast('社区内容不支持批注')"
    />
  </div>
</template>
