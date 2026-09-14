<script setup lang="ts">
/**
 * 移动端 · 书封面（docs/45 §6：书架/书详情共用）。
 *
 * 两种封面（2026-09-14 起）：
 * - **真实封面图**：`cover`（后端 `books.cover_url`）非空 → 渲染 `<img>`；
 *   地址过 `bookCoverUrl()`（补 `PYTHON_BASE`）——打包壳里页面源是 `https://localhost`，
 *   后端在 `http://localhost:8000`，不补基址会让图片打到壳自身的资源服务器上 404；
 *   加载失败自动回退色块（`@error`），不让网络问题把封面变成白块。
 * - **合成封面**（历史口径，`cover_url` 为空时）：色块 + emoji + 书名 + 作者，三本老书行为不变。
 */
import { ref, watch } from 'vue'

import { bookCoverUrl } from '@/api/reading'

const props = withDefaults(
  defineProps<{
    title: string
    color?: string | null
    emoji?: string | null
    author?: string
    /** 真实封面图地址（`books.cover_url`）；为空 → 合成封面 */
    cover?: string | null
  }>(),
  { color: '#16303a', emoji: '📖', author: '', cover: null },
)

const src = ref(bookCoverUrl(props.cover))
const broken = ref(false)
// 换书/换封面时复位：书架列表滚动复用组件实例，不复位会把上一本的失败态带过来
watch(
  () => props.cover,
  (v) => {
    src.value = bookCoverUrl(v)
    broken.value = false
  },
)
</script>

<template>
  <div class="u-bs-card__cover" :style="{ '--cover-color': color ?? '#16303a' }">
    <img
      v-if="src && !broken"
      class="u-bs-card__img"
      :src="src"
      :alt="`《${title}》封面`"
      loading="lazy"
      @error="broken = true"
    >
    <template v-else>
      <span class="u-bs-card__emoji">{{ emoji }}</span>
      <strong class="u-bs-card__title">{{ title }}</strong>
      <span v-if="author" class="u-bs-card__author">{{ author }}</span>
    </template>
  </div>
</template>

