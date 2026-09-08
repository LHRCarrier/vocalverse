<script setup lang="ts">
/**
 * 移动端 · 阅读器底部工具条（docs/45 §6）：章节目录 / 本章批注 / 听书 / 设置。
 */
import MobileIcon from './MobileIcon.vue'

const props = defineProps<{
  ttsActive: boolean
}>()

const emit = defineEmits<{
  'toc': []
  'annotations': []
  'tts': []
  'settings': []
}>()
</script>

<template>
  <nav class="u-rd-bar" aria-label="阅读器工具栏">
    <button class="u-rd-bar__btn" type="button" title="目录" aria-label="目录" @click="emit('toc')">
      <MobileIcon name="book" :size="20" />
      <span>目录</span>
    </button>
    <button class="u-rd-bar__btn" type="button" title="批注" aria-label="批注" @click="emit('annotations')">
      <MobileIcon name="pencil" :size="20" />
      <span>批注</span>
    </button>
    <button
      class="u-rd-bar__btn"
      :class="{ 'is-active': props.ttsActive }"
      type="button"
      title="听书"
      aria-label="听书"
      @click="emit('tts')"
    >
      <MobileIcon name="headphone" :size="20" />
      <span>听书</span>
    </button>
    <button class="u-rd-bar__btn" type="button" title="设置" aria-label="设置" @click="emit('settings')">
      <MobileIcon name="settings" :size="20" />
      <span>设置</span>
    </button>
  </nav>
</template>
