<script setup lang="ts">
/** 404：控制台不暴露任何"资源不存在"的细节（不泄露存在性）。 */
import { RouterLink, useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="nf">
    <div class="nf-card">
      <p class="nf-code c-mono">404</p>
      <h1 class="nf-title">页面不存在</h1>
      <p class="nf-desc c-mono">{{ route.fullPath }}</p>
      <RouterLink class="nf-link" to="/">回到工作台</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.nf {
  display: grid;
  place-items: center;
  min-height: 100vh;
  background: var(--c-bg);
  padding: 24px;
}
.nf-card {
  text-align: center;
  max-width: 420px;
}
.nf-code {
  margin: 0;
  font-size: 40px;
  font-weight: 700;
  color: var(--c-text-3);
  letter-spacing: 0.04em;
}
.nf-title {
  margin: 6px 0 8px;
  font-size: 18px;
  font-weight: 600;
}
.nf-desc {
  margin: 0 0 18px;
  font-size: 12px;
  color: var(--c-text-3);
  word-break: break-all;
}
.nf-link {
  font-size: 13.5px;
  font-weight: 500;
}
</style>
