<script setup lang="ts">
/**
 * 社区卡片 · 帖子容器（docs/34 §4：tweet.dart 粒度对照；S1 真实流）
 *
 * 头部作者行（昵称/@handle/LV/tint 头像）+ 标题/摘要（无标题隐藏，A-01）+
 * 媒体（MobilePostMedia）+ 互动行（MobilePostActions）。
 * kind=checkin：打卡卡分支——整体分 + 今日练习次数 + 日期 mark（docs/37 §8）。
 * 互动状态由 store 维护（乐观更新，docs/34 §7.2）。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import MobileAvatar from '@/components/mobile/MobileAvatar.vue'
import MobilePostActions from '@/components/mobile/MobilePostActions.vue'
import MobilePostMedia from '@/components/mobile/MobilePostMedia.vue'
import { authorDisplay, domainLabel, timeAgo } from '@/api/community'

import type { CommunityPostView } from '@/types/community'

const props = defineProps<{
  post: CommunityPostView
  tintGradient: string
}>()

const emit = defineEmits<{
  'toggle-like': []
  coin: []
  share: []
  'open-comments': []
}>()

const router = useRouter()

/** 打卡卡：整体分展示（后端只回公开面 {overall, practice_count}，C-08） */
const checkinScore = computed(() => props.post.checkinOverall)
const checkinCount = computed(() => props.post.checkinPracticeCount ?? 0)

/** 整卡点击 → 详情页（2026-09-09 修复「点帖子无查看方式」） */
function openDetail() {
  void router.push(`/m/post/${props.post.id}`)
}
</script>

<template>
  <section class="u-comm-item" :aria-label="`${props.post.author.nickname} 的动态`">
    <header class="u-comm-item__head">
      <MobileAvatar
        :src="props.post.author.avatarUrl"
        :name="props.post.author.nickname"
        :tint="props.post.author.tint"
        size="md"
      />
      <span class="u-comm-item__who">
        <span class="u-comm-item__name">
          {{ props.post.author.nickname }}
          <span class="u-comm-item__domain">{{ domainLabel(props.post.domain) }}</span>
        </span>
        <span class="u-comm-item__meta">
          {{ authorDisplay(props.post.author.handle) }} · LV{{ props.post.author.level.slice(1) }} · {{ timeAgo(props.post.createdAt) }}
        </span>
      </span>
    </header>

    <!-- 整卡可点 → 详情页（互动按钮各自 @click.stop，避免误跳） -->
    <div class="u-comm-item__tap" role="button" tabindex="0" :aria-label="`查看内容：${props.post.title ?? props.post.body ?? ''}`" @click="openDetail" @keydown.enter="openDetail">
      <!-- 打卡卡（当日聚合：整体分 + 次数 + 日期） -->
      <template v-if="props.post.kind === 'checkin'">
        <h3 class="u-comm-item__title">今日打卡</h3>
        <p class="u-comm-item__desc">
          完成 {{ checkinCount }} 次口语练习 · 今日综合分
          <strong class="u-comm-item__score">{{ checkinScore == null ? '—' : checkinScore.toFixed(0) }}</strong>
          <time class="u-comm-item__time">{{ props.post.checkinDate }}</time>
        </p>
      </template>

      <template v-else>
        <h3 v-if="props.post.title" class="u-comm-item__title">{{ props.post.title }}</h3>
        <p v-if="props.post.body" class="u-comm-item__desc">{{ props.post.body }}</p>
      </template>

      <MobilePostMedia
        v-if="props.post.media || props.post.kind === 'video'"
        :media="props.post.media"
        :kind="props.post.kind"
        :tint-gradient="props.tintGradient"
        :duration-s="null"
        compact
      />
    </div>

    <MobilePostActions
      :like-count="props.post.likeCount"
      :comment-count="props.post.commentCount"
      :coin-count="props.post.coinCount"
      :share-count="props.post.shareCount"
      :liked="props.post.liked"
      :coined="props.post.coined"
      @toggle-like="emit('toggle-like')"
      @coin="emit('coin')"
      @share="emit('share')"
      @open-comments="emit('open-comments')"
    />
  </section>
</template>
