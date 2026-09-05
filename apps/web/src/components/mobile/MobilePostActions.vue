<script setup lang="ts">
/**
 * 社区卡片 · 互动行（评论 / 点赞 / 投币 / 分享 · X 式）
 * docs/34 §4（tweetIconsRow 粒度）+ docs/31 硬规则 3 三态反馈：
 * 四个操作全部为 button（组长 2026-09-05 升级拍板：互动全交互，演示帧级）。
 * 点赞：is-liked 红 + pop；投币：is-coined 星黄 + pop（--u-star，未新增色）；
 * 评论/分享交由父级打开面板 / 系统分享（计数语义见 pages/community.md）。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'

import type { PostStats } from '@/types/community'

const props = defineProps<{
  stats: PostStats
  liked: boolean
  coined: boolean
}>()

const emit = defineEmits<{
  'toggle-like': []
  'toggle-coin': []
  share: []
  'open-comments': []
}>()

/** 千位缩写：328→328 / 1240→1.2k（X 式浅计数） */
function fmt(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}
</script>

<template>
  <footer class="u-comm-item__foot">
    <button class="u-comm-action" type="button" aria-label="评论" @click="emit('open-comments')">
      <MobileIcon name="chat" :size="15" />
      {{ fmt(props.stats.comment) }}
    </button>
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
    <button
      class="u-comm-action"
      :class="{ 'is-coined': props.coined }"
      type="button"
      :aria-pressed="props.coined"
      :aria-label="props.coined ? '取消投币' : '投币'"
      @click="emit('toggle-coin')"
    >
      <MobileIcon name="coin" :size="15" />
      {{ fmt(props.stats.coin) }}
    </button>
    <button class="u-comm-action" type="button" aria-label="分享" @click="emit('share')">
      <MobileIcon name="share" :size="15" />
      {{ fmt(props.stats.share) }}
    </button>
  </footer>
</template>
