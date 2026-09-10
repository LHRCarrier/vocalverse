<script setup lang="ts">
/**
 * 控制台外壳（docs/50 §11.3）。
 *
 * 这个文件**只负责排布**：侧栏 + 顶栏 + 内容滚动区。
 * 导航裁剪在 `ConsoleSider`，顶栏交互在 `ConsoleHeader`——
 * 布局外壳保持"薄"，改导航不会动到布局（也让它稳在 max-lines 之下）。
 */
import { RouterView } from 'vue-router'

import ConsoleHeader from '@/components/layout/ConsoleHeader.vue'
import ConsoleSider from '@/components/layout/ConsoleSider.vue'
</script>

<template>
  <div class="shell">
    <ConsoleSider />
    <div class="shell-main">
      <ConsoleHeader />
      <main class="shell-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  height: 100vh;
  background: var(--c-bg);
}
.shell-main {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-width: 0;
}
.shell-content {
  flex: 1 1 auto;
  overflow-y: auto;
  min-height: 0;
}
</style>
