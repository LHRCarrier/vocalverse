<script setup lang="ts">
/**
 * 移动端 · 句子选中动作条（2026-09-10 组长拍板：单击句子 → 选中 + 底部动作条）。
 * 色点 = 直接高亮该句（免开弹层）；「批注」= 打开批注弹层写笔记；「听这句」= 从该句开始听书。
 * 2026-09-09：「看批注」= 已批注句子的大热区入口（句首角标只有 ~11px 宽，真机难点中；
 * 这里是 ≥44px 的可靠入口）。
 */
import MobileIcon from './MobileIcon.vue'
import { ANNOTATION_COLORS } from '@/audio/annotation-colors'

const COLORS = ANNOTATION_COLORS

const props = defineProps<{ visible: boolean; hasAnnotation?: boolean }>()

const emit = defineEmits<{
  highlight: [string]
  note: []
  play: []
  'open-note': []
  close: []
}>()
</script>

<template>
  <Transition name="u-sheet">
    <div v-if="visible" class="u-rd-sel" role="toolbar" aria-label="选中句子操作">
      <div class="u-rd-sel__colors">
        <button
          v-for="c in COLORS"
          :key="c.id"
          class="u-rd-sel__dot"
          type="button"
          :style="{ background: c.value }"
          :aria-label="`高亮${c.label}色`"
          :title="`高亮${c.label}色`"
          @click="emit('highlight', c.value)"
        />
      </div>
      <button class="u-rd-sel__btn" type="button" @click="emit('note')">
        <MobileIcon name="pencil" :size="15" />批注
      </button>
      <button v-if="props.hasAnnotation" class="u-rd-sel__btn" type="button" @click="emit('open-note')">
        <MobileIcon name="book" :size="15" />看批注
      </button>
      <button class="u-rd-sel__btn" type="button" @click="emit('play')">
        <MobileIcon name="headphone" :size="15" />听这句
      </button>
      <button class="u-rd-sel__close" type="button" aria-label="取消选中" @click="emit('close')">
        <MobileIcon name="x" :size="15" />
      </button>
    </div>
  </Transition>
</template>
