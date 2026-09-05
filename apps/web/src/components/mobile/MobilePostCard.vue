<script setup lang="ts">
/**
 * 社区卡片 · 帖子容器（docs/34 §4：tweet.dart 粒度对照）
 * 头部作者行 + 标题 + 摘要 + 媒体（MobilePostMedia）+ 互动行（MobilePostActions）。
 * 点赞状态由父级维护（演示帧本地；M3 走后端，见 docs/34 §7.2）。
 */
import MobilePostActions from '@/components/mobile/MobilePostActions.vue'
import MobilePostMedia from '@/components/mobile/MobilePostMedia.vue'

import type { CommunityPost } from '@/types/community'

const props = defineProps<{
  post: CommunityPost
}>()

const emit = defineEmits<{
  'toggle-like': []
}>()
</script>

<template>
  <section class="u-comm-item" :aria-label="`${props.post.author} 的动态`">
    <header class="u-comm-item__head">
      <span class="u-comm-item__ava" :style="{ background: props.post.tint }">{{
        props.post.author.slice(0, 1)
      }}</span>
      <span class="u-comm-item__who">
        <span class="u-comm-item__name">
          {{ props.post.author }}
          <span class="u-comm-item__domain">{{ props.post.domain }}</span>
        </span>
        <span class="u-comm-item__meta">{{ props.post.handle }} · {{ props.post.level }} · {{ props.post.time }}</span>
      </span>
    </header>

    <h3 class="u-comm-item__title">{{ props.post.title }}</h3>
    <p v-if="props.post.desc" class="u-comm-item__desc">{{ props.post.desc }}</p>

    <MobilePostMedia
      v-if="props.post.media"
      :media="props.post.media"
      :kind="props.post.kind"
      :duration="props.post.duration"
    />

    <MobilePostActions
      :stats="props.post.stats"
      :liked="props.post.liked"
      @toggle-like="emit('toggle-like')"
    />
  </section>
</template>
