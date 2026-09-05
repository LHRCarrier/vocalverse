<script setup lang="ts">
/**
 * 社区卡片 · 互动行（评论 / 点赞 / 投币 / 分享 · X 式）
 * docs/34 §4（tweetIconsRow 粒度）+ docs/31 硬规则 3 三态反馈：
 * 点赞 button 有 default/press(:active)/active(is-liked) 三态 + 计数 pop 动画；
 * 分享/评论/投币 = 展示（组长明示，不追加交互）。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'

import type { PostStats } from '@/types/community'

const props = defineProps<{
  stats: PostStats
  liked: boolean
}>()

const emit = defineEmits<{
  'toggle-like': []
}>()

/** 千位缩写：328→328 / 1240→1.2k（X 式浅计数） */
function fmt(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}
</script>

<template>
  <footer class="u-comm-item__foot">
    <span class="u-comm-action">
      <MobileIcon name="chat" :size="15" />
      {{ fmt(props.stats.comment) }}
    </span>
    <button
      class="u-comm-action"
      :class="{ 'is-liked': props.liked }"
      type="button"
      :aria-pressed="props.liked"
      :aria-label="props.liked ? '取消点赞' : '点赞'"
      @click="emit('toggle-like')"
    >
      <MobileIcon name="heart" :size="15" />
      {{ fmt(props.stats.like) }}
    </button>
    <span class="u-comm-action">
      <MobileIcon name="coin" :size="15" />
      {{ fmt(props.stats.coin) }}
    </span>
    <span class="u-comm-action">
      <MobileIcon name="share" :size="15" />
      {{ fmt(props.stats.share) }}
    </span>
  </footer>
</template>
