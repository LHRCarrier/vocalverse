<script setup lang="ts">
/**
 * 社区卡片 · 配图/视频封面（docs/34 §4：tweetImage 粒度对照）
 * 演示：渐变块 + 标签；M3 换真实图片/视频封面（播放行为 M3 接转码流后落地）。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'

import type { CommunityPost, PostMedia } from '@/types/community'

defineProps<{
  media: PostMedia
  kind: CommunityPost['kind']
  duration?: string
}>()
</script>

<template>
  <div
    class="u-comm-media"
    :class="{ 'u-comm-media--video': kind === 'video' }"
    :style="{ background: media.gradient }"
  >
    <!-- 视频封面：播放钮（封面视觉，非可点控件；M3 接播放后改为 button） -->
    <span v-if="kind === 'video'" class="u-comm-media__play" aria-hidden="true">
      <MobileIcon name="play" :size="22" />
    </span>
    <span v-if="duration" class="u-comm-media__dur">{{ duration }}</span>
    <span class="u-comm-media__label">{{ media.label }}</span>
  </div>
</template>
