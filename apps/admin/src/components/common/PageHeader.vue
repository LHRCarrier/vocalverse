<script setup lang="ts">
/** 页头：标题 + 描述 + 右侧主操作。所有页面统一用它，保证视觉节奏一致（docs/50 §11.3）。 */
defineProps<{ title: string; desc?: string }>()
</script>

<template>
  <header class="c-page-head">
    <div>
      <h1 class="c-page-title">{{ title }}</h1>
      <p v-if="desc" class="c-page-desc">{{ desc }}</p>
    </div>
    <div class="c-page-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.c-page-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}
</style>
