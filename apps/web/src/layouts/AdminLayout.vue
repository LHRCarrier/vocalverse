<script setup lang="ts">
import { computed, h } from 'vue'
import { NLayout, NLayoutContent, NLayoutHeader, NLayoutSider, NMenu, NButton } from 'naive-ui'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import type { MenuOption } from 'naive-ui'

const route = useRoute()
const router = useRouter()

const menuOptions: MenuOption[] = [
  { label: '用户管理', key: 'users' },
  { label: '场景库', key: 'scenes' },
  { label: '歌曲库', key: 'songs' },
  { label: '工单', key: 'tickets' },
  { label: '评价看板', key: 'dashboard' },
]

const activeKey = computed(() => String(route.name ?? 'users'))

function renderMenu() {
  return menuOptions.map((o) => ({
    ...o,
    label: () =>
      h(
        RouterLink,
        { to: `/admin/${String(o.key)}` },
        { default: () => String(o.label ?? '') },
      ),
  }))
}

function logout() {
  router.push('/demo')
}
</script>

<template>
  <n-layout class="min-h-screen" has-sider>
    <n-layout-sider bordered collapse-mode="width" :collapsed-width="0" :width="200">
      <div class="flex items-center gap-2 px-4 py-3">
        <span class="inline-block h-3 w-3 rounded-full bg-accent" />
        <span class="font-bold">VocalVerse 管理端</span>
      </div>
      <n-menu :value="activeKey" :options="renderMenu()" />
    </n-layout-sider>
    <n-layout>
      <n-layout-header bordered class="flex items-center justify-end px-4 py-2">
        <NButton quaternary size="small" @click="logout">返回用户端</NButton>
      </n-layout-header>
      <n-layout-content class="p-4">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>
