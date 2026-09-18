<script setup lang="ts">
import { NConfigProvider, NDialogProvider, NMessageProvider } from 'naive-ui'
import { useRouter } from 'vue-router'

import MobileAccountDrawer from '@/components/mobile/MobileAccountDrawer.vue'
import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import { useMotionTier } from '@/composables/useMotionTier'
import { useNativeBack } from '@/composables/useNativeBack'
import { usePageTransition } from '@/composables/usePageTransition'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { themeOverrides } from '@/styles/theme'

import type { RouteLocationNormalizedLoaded } from 'vue-router'

const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()

/** 动效分级：写入 html[data-motion]（high/low/off），供样式侧统一降级（docs/31 规则 4） */
useMotionTier()

/** 页面转场方向（forward/back）：决定微位移符号 */
const { dir } = usePageTransition(router)

/**
 * 哪些路由走页面转场：仅移动端真形态 `/m/*`。
 * - `/login` 与桌面子树（UserLayout）直出，避免双重转场；
 * - 阅读器（`/m/reader/*`）是沉浸页、自带滚动容器，排除以免转场期定位影响长文。
 */
function pageAnimated(route: RouteLocationNormalizedLoaded): boolean {
  return route.path.startsWith('/m/') && !route.path.startsWith('/m/reader')
}

/** Android 返回手势/按键：抽屉开着就先关抽屉（阅读器弹层由各页自己注册，见 useNativeBack） */
useNativeBack(() => {
  if (!ui.drawerOpen) return false
  ui.closeDrawer()
  return true
})

/** 全局抽屉导航（任意页面头像 → 抽屉 → 菜单项） */
function onDrawerNavigate(path: string) {
  ui.closeDrawer()
  void router.push(path)
}

function onDrawerLogout() {
  ui.closeDrawer()
  // 服务端吊销该用户全部 refresh token + 清本地（2026-09-07：原 clear() 只清本地，token 30 天仍可续命）
  void auth.logout()
  // SPA 导航（整刷丢失过渡；body 背景由 router.afterEach 的 .is-login 类管理，2026-09-06 修退出后登录页错位）
  void router.push('/login')
}
</script>

<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-dialog-provider>
      <n-message-provider>
        <!-- 页面转场容器（定位上下文：leave 期旧页脱离文档流，避免撑高/滚动跳变） -->
        <div class="m-page-wrap">
          <router-view v-slot="{ Component, route }">
            <Transition v-if="pageAnimated(route)" :name="`m-page-${dir}`">
              <component :is="Component" :key="route.path" />
            </Transition>
            <component :is="Component" v-else />
          </router-view>
        </div>

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
