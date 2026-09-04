<script setup lang="ts">
/** 移动端底部浮动 Tab 栏（Home / Speaking / 主按钮 / Songs / Me）——原型 app-home 组件。 */
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()

function logout() {
  auth.clear()
  window.location.href = '/login'
}
</script>

<template>
  <nav class="u-tabbar">
    <RouterLink to="/m/home" class="u-tab" :class="{ active: route.path === '/m/home' }">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <path d="M4 20V4M4 20h16" /><path d="M8 16v-5M12 16V7M16 16v-3" />
      </svg>
      Home
    </RouterLink>
    <RouterLink to="/m/speaking" class="u-tab" :class="{ active: route.path.startsWith('/m/chat') }">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
      </svg>
      Speaking
    </RouterLink>
    <RouterLink to="/m/chat" class="main" title="新会话">
      <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <path d="M12 4.5v9M7.5 9h9" />
      </svg>
    </RouterLink>
    <RouterLink to="/sing" class="u-tab" :class="{ active: route.path === '/sing' }">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <path d="M9 18V6l10-2v12" /><circle cx="6.5" cy="18" r="2.5" /><circle cx="16.5" cy="16" r="2.5" />
      </svg>
      Songs
    </RouterLink>
    <button class="u-tab" :class="{ active: route.path === '/m/me' }" type="button" title="退出登录" @click="logout">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <circle cx="12" cy="8.5" r="3.5" /><path d="M5 20a7 7 0 0 1 14 0" />
      </svg>
      Me
    </button>
  </nav>
</template>
