<script setup lang="ts">
/**
 * 移动端 · 书封面色块（docs/45 §6：书架/书详情共用；无图封面 = 色块 + emoji + 书名。
 * 背景由调用方以 --cover-color 注入（默认深青 #16303a，u-* 暗部色板）。
 */
withDefaults(
  defineProps<{
    title: string
    color?: string | null
    emoji?: string | null
    author?: string
  }>(),
  { color: '#16303a', emoji: '📖', author: '' },
)
</script>

<template>
  <div class="u-bs-card__cover" :style="{ '--cover-color': color ?? '#16303a' }">
    <span class="u-bs-card__emoji">{{ emoji }}</span>
    <strong class="u-bs-card__title">{{ title }}</strong>
    <span v-if="author" class="u-bs-card__author">{{ author }}</span>
  </div>
</template>
