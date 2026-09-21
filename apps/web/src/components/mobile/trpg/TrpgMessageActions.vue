<script setup lang="ts">
/**
 * 酒馆 · 消息长按操作菜单（底部动作条；替代气泡尾重播按钮）。
 *
 * 选项（按角色裁剪）：
 * - 听这句 / 停止朗读（DM 且 voice 可合成时）；
 * - 标注 / 取消标注（本地标记，跨刷新保留）；
 * - 复制文本；
 * - 取消。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'

const props = withDefaults(
  defineProps<{
    open: boolean
    role: 'user' | 'assistant'
    marked?: boolean
    /** 该条是否正在朗读（用于按钮文案「停止朗读」） */
    playing?: boolean
    /** 是否有可读文本（纯系统卡不显示「听这句」；由父级传 false） */
    speakable?: boolean
  }>(),
  { marked: false, playing: false, speakable: true },
)

const emit = defineEmits<{
  close: []
  listen: []
  'toggle-mark': []
  copy: []
}>()
</script>

<template>
  <div v-if="props.open" class="t-sheet">
    <div class="t-sheet__backdrop" role="presentation" @click="emit('close')" />
    <section class="t-sheet__panel t-sheet__panel--short" role="dialog" aria-label="消息操作">
      <header class="t-sheet__head">
        <div class="t-sheet__title">{{ props.role === 'assistant' ? 'DM 消息' : '我的消息' }}</div>
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
        <button class="t-act" type="button" @click="emit('toggle-mark')">
          <MobileIcon name="bookmark" :size="18" />
          {{ props.marked ? '取消标注' : '标注这条' }}
        </button>
        <button class="t-act" type="button" @click="emit('copy')">
          <MobileIcon name="note" :size="18" />
          复制文本
        </button>
        <button class="u-btn u-btn--secondary u-btn--block" type="button" @click="emit('close')">
          取消
        </button>
      </div>
    </section>
  </div>
</template>
