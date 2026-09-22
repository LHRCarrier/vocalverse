<script setup lang="ts">
/**
 * 导航图标（编译期内联；映射表在 ./navIcons.ts，便于回归测试消费）。
 *
 * 未知图标名渲染空位而非报错：新增菜单项忘记登记图标时不该白屏
 * （回归由 `__tests__/navIcon.test.ts` 兜底，把「静默空白」变成构建期红灯）。
 */
import { NAV_ICONS } from './navIcons'

defineProps<{ name: string; size?: number }>()
</script>

<template>
  <component
    :is="NAV_ICONS[name]"
    v-if="NAV_ICONS[name]"
    :width="size ?? 18"
    :height="size ?? 18"
    aria-hidden="true"
  />
</template>
