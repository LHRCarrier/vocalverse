<script setup lang="ts">
import { NConfigProvider, NDialogProvider, NMessageProvider } from 'naive-ui'
import { useRouter } from 'vue-router'

import MobileAccountDrawer from '@/components/mobile/MobileAccountDrawer.vue'
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
  window.location.href = '/login'
}
</script>

<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-dialog-provider>
      <n-message-provider>
        <router-view />

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
