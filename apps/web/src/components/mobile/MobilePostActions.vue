<script setup lang="ts">
/**
 * 社区卡片 · 互动行（评论 / 点赞 / 支持 / 分享 · X 式；S1 真实流）
 *
 * docs/34 §4（tweetIconsRow 粒度）+ docs/31 硬规则 3 三态反馈：四个操作全部 button。
 * - 点赞：is-liked 红 + pop；可取消（toggle）；
 * - 支持（原「投币」A-10/D-Q2）：**不可取消、一人一帖一次**——已支持再点不双计（store 幂等提示）；
 * - 评论/分享交由父级（面板 / 系统分享）。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { fmtCount } from '@/api/community'

const props = defineProps<{
  likeCount: number
  commentCount: number
  coinCount: number
  shareCount: number
  liked: boolean
  coined: boolean
}>()

const emit = defineEmits<{
  'toggle-like': []
  coin: []
  share: []
  'open-comments': []
}>()
</script>

<template>
  <footer class="u-comm-item__foot">
    <button class="u-comm-action" type="button" aria-label="评论" @click="emit('open-comments')">
      <MobileIcon name="chat" :size="15" />
      {{ fmtCount(props.commentCount) }}
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
      {{ fmtCount(props.likeCount) }}
    </button>
    <button
      class="u-comm-action"
      :class="{ 'is-coined': props.coined }"
      type="button"
      :aria-pressed="props.coined"
      :aria-label="props.coined ? '已支持（不可取消）' : '支持'"
      :title="props.coined ? '已支持 · 支持不可取消' : '支持（原投币）· 不可取消'"
      @click="emit('coin')"
    >
      <MobileIcon name="coin" :size="15" />
      {{ fmtCount(props.coinCount) }}
    </button>
    <button class="u-comm-action" type="button" aria-label="分享" @click="emit('share')">
      <MobileIcon name="share" :size="15" />
      {{ fmtCount(props.shareCount) }}
    </button>
  </footer>
</template>
