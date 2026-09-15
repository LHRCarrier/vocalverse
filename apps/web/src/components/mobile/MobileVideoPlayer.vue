<script setup lang="ts">
/**
 * 移动端 · 视频播放器（社区 S3 · docs/47 §5.2）
 *
 * 原生 `<video>` + 自绘进度条/播放钮：视频流由 Python `GET /api/v1/media/{id}` 提供，
 * Starlette `FileResponse` 支持 Range/206 → 拖动进度条只拉需要的片段。
 *
 * 封面：`poster` 用服务端 media.coverUrl；客户端首帧抓帧（待定项 D 裁定）本期不做
 * （需要 canvas + 跨域头，收益低）→ 无封面时用渐变底。
 */
import { computed, onBeforeUnmount, ref } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { mediaUrl } from '@/api/media'

const props = defineProps<{
  url: string
  poster?: string | null
  tintGradient?: string
  /** 初始是否自动播放（默认否：移动端浏览器普遍拦截带声自动播放） */
  autoplay?: boolean
}>()

const videoEl = ref<HTMLVideoElement | null>(null)
const playing = ref(false)
const loading = ref(true)
const failed = ref(false)
const progress = ref(0)
const duration = ref(0)
const currentTime = ref(0)

const posterUrl = computed(() => mediaUrl(props.poster))
const srcUrl = computed(() => mediaUrl(props.url))

function toggle() {
  const el = videoEl.value
  if (!el) return
  if (el.paused) void el.play().catch(() => (failed.value = false))
  else el.pause()
}

function onLoaded() {
  loading.value = false
  duration.value = videoEl.value?.duration ?? 0
}

function onTimeUpdate() {
  const el = videoEl.value
  if (!el || !el.duration) return
  currentTime.value = el.currentTime
  progress.value = el.currentTime / el.duration
}

function seek(e: MouseEvent) {
  const el = videoEl.value
  if (!el || !el.duration) return
  const bar = e.currentTarget as HTMLElement
  const ratio = Math.min(1, Math.max(0, (e.clientX - bar.getBoundingClientRect().left) / bar.clientWidth))
  el.currentTime = ratio * el.duration
}

function fmt(s: number): string {
  if (!Number.isFinite(s) || s <= 0) return '0:00'
  const m = Math.floor(s / 60)
  return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`
}

onBeforeUnmount(() => videoEl.value?.pause())
</script>

<template>
  <div class="u-vp" :style="{ background: props.tintGradient ?? 'var(--u-track)' }">
    <video
      ref="videoEl"
      class="u-vp__video"
      :src="srcUrl"
      :poster="posterUrl || undefined"
      :autoplay="props.autoplay"
      playsinline
      preload="metadata"
      controlslist="nodownload"
      @loadedmetadata="onLoaded"
      @waiting="loading = true"
      @playing="loading = false; playing = true"
      @pause="playing = false"
      @ended="playing = false"
      @timeupdate="onTimeUpdate"
      @error="failed = true; loading = false"
    />

    <!-- 自绘播放钮（原生 controls 在深色底上对比不足；仅在未播放时覆盖） -->
    <button
      v-if="!playing"
      class="u-vp__play"
      type="button"
      aria-label="播放视频"
      :disabled="failed"
      @click="toggle"
    >
      <MobileIcon :name="failed ? 'info' : 'play'" :size="26" />
    </button>

    <p v-if="failed" class="u-vp__err" role="status" aria-live="polite">视频加载失败，请稍后重试</p>
    <p v-else-if="loading" class="u-vp__err" role="status" aria-live="polite">视频加载中…</p>

    <div class="u-vp__bar">
      <button class="u-vp__toggle" type="button" :aria-label="playing ? '暂停' : '播放'" @click="toggle">
        <MobileIcon :name="playing ? 'pause' : 'play'" :size="16" />
      </button>
      <span class="u-vp__track" role="slider" :aria-valuenow="Math.round(progress * 100)" aria-label="播放进度" tabindex="0" @click="seek">
        <span class="u-vp__fill" :style="{ width: `${progress * 100}%` }" />
      </span>
      <span class="u-vp__time">{{ fmt(currentTime) }} / {{ fmt(duration) }}</span>
    </div>
  </div>
</template>
