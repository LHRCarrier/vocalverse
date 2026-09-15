<script setup lang="ts">
/**
 * 移动端 · 媒体宫格（社区 S3 · docs/47 §5.2）
 *
 * X 式布局：1 张按原比例（限高）、2 张并排、3 张 = 1 大 + 2 小、4 张 2×2、≥5 张 3 列方裁；
 * 列表页只渲首图 + 角标（`compact`），详情页渲全量（docs/47 §6「feed 放大」）。
 *
 * 图片地址一律过 `mediaUrl()`（打包壳里相对路径会打到 https://localhost，docs/48 B5）；
 * 加载失败 → 占位块 + 「图片加载失败」文案（不静默 display:none，docs/48 B18）。
 */
import { computed } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { mediaUrl } from '@/api/media'

import type { NormalizedMedia, PostMediaItem } from '@/types/community'

const props = withDefaults(
  defineProps<{
    media: NormalizedMedia
    /** 列表卡模式：只渲首图 + 「+N」角标 */
    compact?: boolean
    /** 渐变兜底（作者 tint 派生；无 url 时用） */
    tintGradient?: string
  }>(),
  { compact: false, tintGradient: 'linear-gradient(135deg, #37546e, #6e96b4)' },
)

const emit = defineEmits<{
  /** 点第 i 张 → 打开灯箱 */
  open: [number]
  /** 点视频 → 打开播放器 */
  play: []
}>()

const items = computed<PostMediaItem[]>(() => props.media.items)
const isVideo = computed(() => props.media.kind === 'video')
const shown = computed<PostMediaItem[]>(() => {
  if (isVideo.value) return []
  return props.compact ? items.value.slice(0, 1) : items.value
})
const extra = computed(() => (props.compact ? Math.max(0, items.value.length - 1) : 0))
const gridClass = computed(() => {
  const n = shown.value.length
  if (n <= 1) return 'is-one'
  if (n === 2) return 'is-two'
  if (n === 3) return 'is-three'
  if (n === 4) return 'is-four'
  return 'is-many'
})

function durationText(s: number | null): string {
  if (s == null) return ''
  const m = Math.floor(s / 60)
  return `${m}:${String(Math.round(s % 60)).padStart(2, '0')}`
}

function onImgError(e: Event) {
  const el = e.target as HTMLImageElement
  el.classList.add('is-broken')
  el.dataset.broken = '1'
}
</script>

<template>
  <!-- 视频：封面 + 播放钮（详情页点开播放器；列表页同样给播放入口） -->
  <div
    v-if="isVideo"
    class="u-media u-media--video"
    :style="{ background: props.tintGradient }"
    role="button"
    tabindex="0"
    aria-label="播放视频"
    @click="emit('play')"
    @keydown.enter="emit('play')"
  >
    <img
      v-if="props.media.coverUrl"
      class="u-media__img"
      :src="mediaUrl(props.media.coverUrl)"
      alt="视频封面"
      loading="lazy"
      decoding="async"
      @error="onImgError"
    >
    <span class="u-media__play"><MobileIcon name="play" :size="22" /></span>
    <span v-if="props.media.durationS" class="u-media__dur">{{ durationText(props.media.durationS) }}</span>
  </div>

  <!-- 无媒体：渐变占位（S1 种子视频/纯文本帖） -->
  <div
    v-else-if="shown.length === 0"
    class="u-media u-media--empty"
    :style="{ background: props.tintGradient }"
    aria-hidden="true"
  >
    <span class="u-media__label">🖼️ PHOTO</span>
  </div>

  <!-- 图片宫格 -->
  <div v-else class="u-media-grid" :class="gridClass">
    <button
      v-for="(it, i) in shown"
      :key="it.id ?? `${it.url}-${i}`"
      class="u-media-grid__cell"
      type="button"
      :aria-label="`查看第 ${i + 1} 张图片`"
      @click="emit('open', i)"
    >
      <img
        class="u-media-grid__img"
        :src="mediaUrl(it.url)"
        :alt="`配图 ${i + 1}`"
        loading="lazy"
        decoding="async"
        @error="onImgError"
      >
      <span v-if="extra && i === shown.length - 1" class="u-media-grid__more">+{{ extra }}</span>
    </button>
  </div>
</template>
