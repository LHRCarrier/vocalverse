<script setup lang="ts">
/**
 * 酒馆 · 消息长按操作菜单（底部动作条；替代气泡尾重播按钮）。
 *
 * 选项（按角色裁剪）：
 * - 听这句 / 停止朗读（DM 且 voice 可合成时）；
 * - 翻译（中英互切；已翻译时可看原文）；
 * - 标注 / 取消标注（本地标记，跨刷新保留）；
 * - 复制文本；
 * - 取消。
 * 头部带**所选消息预览**（解决「长按了不知道选的是哪条」）。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'

const props = withDefaults(
  defineProps<{
    open: boolean
    role: 'user' | 'assistant'
    /** 所选消息预览（首 48 字，单行省略） */
    preview?: string
    marked?: boolean
    /** 该条是否正在朗读（用于按钮文案「停止朗读」） */
    playing?: boolean
    /** 是否有可读文本（纯系统卡不显示「听这句」；由父级传 false） */
    speakable?: boolean
    /** 译文状态：已展示译文时菜单项显示「看原文」 */
    translated?: boolean
  }>(),
  { preview: '', marked: false, playing: false, speakable: true, translated: false },
)

const emit = defineEmits<{
  close: []
  listen: []
  translate: []
  'toggle-mark': []
  copy: []
}>()
</script>

<template>
  <div v-if="props.open" class="t-sheet">
    <div class="t-sheet__backdrop" role="presentation" @click="emit('close')" />
    <section class="t-sheet__panel t-sheet__panel--short" role="dialog" aria-label="消息操作">
      <header class="t-sheet__head">
        <div class="t-sheet__head-main">
          <div class="t-sheet__title">{{ props.role === 'assistant' ? 'DM 消息' : '我的消息' }}</div>
          <div v-if="props.preview" class="t-act__quote">「{{ props.preview }}」</div>
        </div>
        <button
          class="t-sheet__close"
          type="button"
          title="关闭"
          aria-label="关闭"
          @click="emit('close')"
        >
          <MobileIcon name="x" :size="18" />
        </button>
      </header>
      <div class="t-sheet__body">
        <button
          v-if="props.role === 'assistant' && props.speakable"
          class="t-act"
          type="button"
          @click="emit('listen')"
        >
          <MobileIcon :name="props.playing ? 'stop' : 'volume'" :size="18" />
          {{ props.playing ? '停止朗读' : '听这句' }}
        </button>
        <button class="t-act" type="button" @click="emit('translate')">
          <MobileIcon name="hash" :size="18" />
          {{ props.translated ? '看原文' : '翻译这条' }}
        </button>
        <button class="t-act" type="button" @click="emit('toggle-mark')">
          <MobileIcon name="bookmark" :size="18" />
          {{ props.marked ? '取消标注' : '标注这条' }}
        </button>
        <button class="t-act" type="button" @click="emit('copy')">
          <MobileIcon name="copy" :size="18" />
          复制文本
        </button>
        <button class="u-btn u-btn--secondary u-btn--block" type="button" @click="emit('close')">
          取消
        </button>
      </div>
    </section>
  </div>
</template>
