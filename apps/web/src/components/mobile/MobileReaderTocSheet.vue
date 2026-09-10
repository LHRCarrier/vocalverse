<script setup lang="ts">
/**
 * 移动端 · 阅读器目录弹层（docs/45 §6 · v1 精简：提示回详情页换章）。
 */
import MobileIcon from './MobileIcon.vue'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [boolean]; close: [] }>()
</script>

<template>
  <Teleport to="body">
    <Transition name="u-sheet">
      <div v-if="open" class="u-sheet-mask" @click.self="emit('update:open', false)">
        <div class="u-sheet">
          <header class="u-sheet__head">
            <h2 class="u-sheet__title">目录</h2>
            <button class="u-sheet__close" type="button" aria-label="关闭" @click="emit('close')">
              <MobileIcon name="x" :size="18" />
            </button>
          </header>
          <p class="u-comm-empty__sub">章节切换请回到书籍详情页（v1 精简路径）。</p>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
