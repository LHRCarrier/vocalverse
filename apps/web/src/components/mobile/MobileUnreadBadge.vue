<script setup lang="ts">
/**
 * 未读数字角标（docs/49 §4.1：>0 才显示、>99 → 99+；色用 --u-accent——
 * 本项目红色是错误语义，不用红点）。父级需 position: relative。
 */
import { computed } from 'vue'

const props = defineProps<{ count: number }>()

const text = computed(() => (props.count > 99 ? '99+' : String(props.count)))
</script>

<template>
  <span v-if="props.count > 0" class="u-badge" :aria-label="`${props.count} 条未读`">{{ text }}</span>
</template>
