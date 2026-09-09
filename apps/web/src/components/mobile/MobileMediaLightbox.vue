<script setup lang="ts">
/**
 * 移动端 · 图片灯箱（社区 S3 · docs/47 §5.2）
 *
 * 不复用 `.u-sheet-mask`（它是 `align-items:flex-end` + `.u-sheet{max-width:480px}`，做不了全屏），
 * 自绘 `--u-scrim` 底 + body 滚动锁。
 *
 * 交互：左右滑切图（`touch-action: pan-y` + pointer 拖拽）/ 点遮罩或 × 关闭 /
 * 安卓返回键关闭（由父级注册进 `useNativeBack` 层序 —— 否则返回直接退页，docs/48 B14）。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { mediaUrl } from '@/api/media'

import type { PostMediaItem } from '@/types/community'

const props = defineProps<{
  open: boolean
  items: PostMediaItem[]
  index: number
}>()

const emit = defineEmits<{
  'update:open': [boolean]
  'update:index': [number]
}>()

const current = computed(() => props.items[props.index] ?? null)
const dragX = ref(0)
const dragging = ref(false)
let startX = 0
let startY = 0

function close() {
  emit('update:open', false)
}

function step(delta: number) {
  const next = props.index + delta
  if (next >= 0 && next < props.items.length) emit('update:index', next)
}

function onPointerDown(e: PointerEvent) {
  dragging.value = true
  startX = e.clientX
  startY = e.clientY
  dragX.value = 0
}

function onPointerMove(e: PointerEvent) {
  if (!dragging.value) return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  // 纵向优先 → 不抢页面滚动
  if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 12) {
    dragging.value = false
    dragX.value = 0
    return
  }
  dragX.value = dx
}

function onPointerUp() {
  if (!dragging.value) return
  dragging.value = false
  const dx = dragX.value
  dragX.value = 0
  if (Math.abs(dx) > 60) step(dx < 0 ? 1 : -1)
}

/** body 滚动锁（全仓此前没有 scroll-lock；灯箱开着还能滚底层列表） */
function lockBody(lock: boolean) {
  document.body.style.overflow = lock ? 'hidden' : ''
}

watch(
  () => props.open,
  (v) => lockBody(v),
  { immediate: true },
)
onBeforeUnmount(() => lockBody(false))
</script>

<template>
  <Teleport to="body">
    <Transition name="u-sheet">
      <div
        v-if="props.open && current"
        class="u-lb"
        role="dialog"
        aria-modal="true"
        aria-label="查看图片"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
        @click.self="close"
      >
        <header class="u-lb__bar">
          <span class="u-lb__count">{{ props.index + 1 }} / {{ props.items.length }}</span>
          <button class="u-lb__close" type="button" aria-label="关闭" @click="close">
            <MobileIcon name="x" :size="20" />
          </button>
        </header>

        <img
          class="u-lb__img"
          :src="mediaUrl(current.url)"
          :alt="`图片 ${props.index + 1}`"
          :style="{ transform: `translateX(${dragX}px)` }"
          decoding="async"
        >

        <button
          v-if="props.index > 0"
          class="u-lb__nav u-lb__nav--prev"
          type="button"
          aria-label="上一张"
          @click.stop="step(-1)"
        >
          <MobileIcon name="back" :size="20" />
        </button>
        <button
          v-if="props.index < props.items.length - 1"
          class="u-lb__nav u-lb__nav--next"
          type="button"
          aria-label="下一张"
          @click.stop="step(1)"
        >
          <MobileIcon name="arrow" :size="20" />
        </button>
      </div>
    </Transition>
  </Teleport>
</template>
