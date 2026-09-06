<script setup lang="ts">
import { NConfigProvider, NDialogProvider, NMessageProvider } from 'naive-ui'
import { useRouter } from 'vue-router'

import MobileAccountDrawer from '@/components/mobile/MobileAccountDrawer.vue'
import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { themeOverrides } from '@/styles/theme'

const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()

/** 全局抽屉导航（任意页面头像 → 抽屉 → 菜单项） */
function onDrawerNavigate(path: string) {
  ui.closeDrawer()
  void router.push(path)
}

function onDrawerLogout() {
  ui.closeDrawer()
  auth.clear()
  // SPA 导航（整刷丢失过渡；body 背景由 router.afterEach 的 .is-login 类管理，2026-09-06 修退出后登录页错位）
  void router.push('/login')
}
</script>

<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-dialog-provider>
      <n-message-provider>
        <router-view />

        <!-- 全局底部 Tab 栏（路由显隐规则在组件内；二级页自动隐藏） -->
        <MobileTabBar />

        <!-- 全局账户抽屉 + 全局 toast（2026-09-05：任意页面头像可开；各页不再自建 toast） -->
        <MobileAccountDrawer
          :open="ui.drawerOpen"
          :me="auth.me"
          @update:open="ui.closeDrawer()"
          @navigate="onDrawerNavigate"
          @logout="onDrawerLogout"
        />
        <div v-if="ui.toastText" class="u-toast show"><span class="dot" aria-hidden="true" />{{ ui.toastText }}</div>
      </n-message-provider>
    </n-dialog-provider>
  </n-config-provider>
</template>
