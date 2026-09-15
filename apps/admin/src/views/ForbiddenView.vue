<script setup lang="ts">
/**
 * 403：已登录但**没有该页所需权限**。
 *
 * 为什么与 401 分开：混在一起会让用户反复"重新登录"却依然进不去（登录态是好的），
 * 这里直接告诉他缺哪个权限码，便于找超级管理员开权限（docs/50 §4.3）。
 */
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { NAV_GROUPS } from '@/router/nav'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()

const from = computed(() => (typeof route.query.from === 'string' ? route.query.from : ''))
const firstAllowed = computed(
  () => NAV_GROUPS.flatMap((g) => g.items).find((i) => auth.hasPermission(i.permission ?? null))?.path ?? '/',
)
</script>

<template>
  <div class="fb">
    <div class="fb-card">
      <h1 class="fb-title">没有访问权限</h1>
      <p class="fb-desc">
        当前账号
        <strong>{{ auth.profile?.displayName ?? '—' }}</strong>
        （角色 {{ auth.profile?.roleName || auth.profile?.roleCode || '—' }}）没有该页所需权限。
      </p>
      <p v-if="from" class="fb-path c-mono">{{ from }}</p>
      <p class="fb-hint">如需访问，请联系超级管理员在「系统 · 角色权限」中为你的角色勾选对应权限码。</p>
      <RouterLink class="fb-link" :to="firstAllowed">返回可访问页面</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.fb {
  display: grid;
  place-items: center;
  min-height: 100vh;
  background: var(--c-bg);
  padding: 24px;
}
.fb-card {
  max-width: 460px;
  background: var(--c-surface);
  border-radius: var(--c-card-radius);
  box-shadow: var(--c-shadow-2);
  padding: 28px 30px;
}
.fb-title {
  margin: 0 0 10px;
  font-size: 18px;
  font-weight: 600;
}
.fb-desc {
  margin: 0 0 8px;
  font-size: 13.5px;
  color: var(--c-text-2);
  line-height: 1.6;
}
.fb-path {
  margin: 0 0 10px;
  padding: 5px 9px;
  border-radius: var(--c-ctl-radius);
  background: var(--c-surface-sunken);
  color: var(--c-text-2);
}
.fb-hint {
  margin: 0 0 18px;
  font-size: 12.5px;
  color: var(--c-text-3);
  line-height: 1.6;
}
.fb-link {
  font-size: 13.5px;
  font-weight: 500;
}
</style>
