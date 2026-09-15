<script setup lang="ts">
/**
 * 移动端 · 听书播放条（docs/45 §6 · UI 拷问 U 系列：句级高亮跟随的浮动条）。
 * 纯展示组件：音频编排在 useChapterTts（视图层持有），组件只反映状态。
 */
import MobileIcon from './MobileIcon.vue'

const props = defineProps<{
  label: string
  playing: boolean
  progress: number
  rate: number
  /** 预合成/加载中提示（可空） */
  busyText?: string
}>()

const emit = defineEmits<{
  toggle: []
  prev: []
  next: []
  'change-rate': []
  close: []
}>()

function rateLabel(r: number): string {
  return `${r}x`
}
</script>

<template>
  <div class="u-rd-tts" role="group" aria-label="听书控制">
    <button class="u-rd-tts__icon" type="button" title="上一句" aria-label="上一句" @click="emit('prev')">
      <MobileIcon name="skip-back" :size="16" />
    </button>
    <button
      class="u-rd-tts__icon is-primary"
      type="button"
      :title="props.playing ? '暂停' : '播放'"
      :aria-label="props.playing ? '暂停' : '播放'"
      @click="emit('toggle')"
    >
      <MobileIcon :name="props.playing ? 'pause' : 'play'" :size="18" />
    </button>
    <button class="u-rd-tts__icon" type="button" title="下一句" aria-label="下一句" @click="emit('next')">
      <MobileIcon name="skip-forward" :size="16" />
    </button>
    <div class="u-rd-tts__body">
      <div class="u-rd-tts__label">{{ props.busyText ?? props.label }}</div>
      <div class="u-rd-tts__progress" role="progressbar" :aria-valuenow="Math.round(props.progress * 100)">
        <span class="u-rd-tts__fill" :style="{ width: `${Math.min(100, Math.max(0, props.progress * 100))}%` }" />
      </div>
    </div>
    <button class="u-rd-tts__rate" type="button" :title="`倍速 ${rateLabel(props.rate)}`" @click="emit('change-rate')">
      {{ rateLabel(props.rate) }}
    </button>
    <button class="u-rd-tts__icon" type="button" title="关闭听书" aria-label="关闭听书" @click="emit('close')">
      <MobileIcon name="x" :size="16" />
    </button>
  </div>
</template>
