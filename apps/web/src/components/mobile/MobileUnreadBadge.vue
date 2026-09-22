<script setup lang="ts">
/**
 * 未读数字角标（docs/49 §4.1：>0 才显示、>99 → 99+；色用 --u-accent——
 * 本项目红色是错误语义，不用红点）。父级需 position: relative。
 *
 * 类名 `.u-unread`（2026-09-22）：原用共享状态徽标类 `.u-badge`，把歌单行的状态徽标
 * 一起改成了绝对定位的蓝角标（真机「可跟唱」叠在列表右上角）。样式见 `mobile-uic.css`。
 */
import { computed } from 'vue'

const props = defineProps<{ count: number }>()

const text = computed(() => (props.count > 99 ? '99+' : String(props.count)))
</script>

<template>
  <span v-if="props.count > 0" class="u-unread" :aria-label="`${props.count} 条未读`">{{ text }}</span>
</template>
