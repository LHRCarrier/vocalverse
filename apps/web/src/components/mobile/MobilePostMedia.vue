<script setup lang="ts">
/**
 * 社区卡片 · 配图/视频封面（docs/34 §4：tweetImage 粒度对照；S1 真实流）
 *
 * 媒体来自后端 media jsonb（字段集对齐 MediaItem：type/url/coverUrl/duration_s…，
 * C-06/D-Q1）；无 url 时渐变占位（作者 tint 派生）；视频=封面+时长+播放角标
 * （点击给「视频播放 S3 上线」反馈，A-13）；外链失效 onerror 降级渐变（B-12）。
 */
import { computed } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { formatDuration } from '@/api/community'
import { useUiStore } from '@/stores/ui'

import type { CommunityPostView } from '@/types/community'

const props = defineProps<{
  media: CommunityPostView['media'] | null
  kind: CommunityPostView['kind']
  tintGradient: string
  durationS?: number | null
}>()

const ui = useUiStore()

/** 媒体类型（后端 type；无媒体时按 kind 兜底） */
const mediaType = computed<'video' | 'image' | 'none'>(() => {
  if (props.media?.type === 'video' || props.kind === 'video') return 'video'
  if (props.media?.type === 'image' || props.media?.url) return 'image'
  return 'none'
})

const label = computed(() => {
  if (mediaType.value === 'video') return '🎬 VIDEO'
  if (mediaType.value === 'image') return '🖼️ PHOTO'
  return props.kind === 'checkin' ? '🔥 CHECK-IN' : '📰 POST'
})

const durationText = computed(() => formatDuration(props.durationS ?? props.media?.durationS))

function onPlayClick() {
  ui.showToast('视频播放 S3 上线')
}
</script>

<template>
  <div
    class="u-comm-media"
    :class="{ 'u-comm-media--video': mediaType === 'video' }"
    :style="{ background: props.tintGradient }"
  >
    <!-- 真实图片（外链；onerror 降级渐变占位） -->
    <img
      v-if="mediaType === 'image' && (props.media?.url || props.media?.coverUrl)"
      class="u-comm-media__img"
      :src="props.media?.coverUrl ?? props.media?.url ?? ''"
      :alt="props.kind === 'video' ? '视频封面' : '配图'"
      loading="lazy"
      @error="($event.target as HTMLImageElement).style.display = 'none'"
    >

    <!-- 视频封面：播放钮（可点，反馈占位 toast） -->
    <button
      v-if="mediaType === 'video'"
      class="u-comm-media__play"
      type="button"
      aria-label="播放视频"
      @click="onPlayClick"
    >
      <MobileIcon name="play" :size="22" />
    </button>

    <span v-if="mediaType === 'video' && durationText" class="u-comm-media__dur">{{ durationText }}</span>
    <span class="u-comm-media__label">{{ label }}</span>
  </div>
</template>
