<script setup lang="ts">
import { computed, h } from 'vue'
import { NLayout, NLayoutContent, NLayoutSider, NMenu, NTag } from 'naive-ui'
import { RouterLink, useRoute } from 'vue-router'

import type { MenuOption } from 'naive-ui'

import { previewPages } from './registry'

const route = useRoute()
const activeKey = computed(() => String(route.path))

const groups = ['用户端', '管理端'] as const

function renderMenu(): MenuOption[] {
  return groups.map((group) => ({
    type: 'group',
    label: group,
    key: group,
    children: previewPages
      .filter((p) => p.group === group)
      .map((p) => ({
        key: p.path,
        label: () =>
          h(RouterLink, { to: p.path, class: 'block w-full' }, { default: () => p.label }),
      })),
  }))
}
</script>

<template>
  <n-layout class="min-h-screen" has-sider>
    <n-layout-sider bordered :width="240" content-class="flex flex-col">
      <div class="flex items-center gap-2 px-4 py-3">
        <span class="inline-block h-3 w-3 rounded-full bg-accent" />
        <span class="font-bold">前端预览画廊</span>
        <NTag size="small" type="warning">DEV ONLY</NTag>
      </div>
      <n-menu :value="activeKey" :options="renderMenu()" />
      <div class="mt-auto border-t border-[#E5E7EB] px-4 py-3 text-xs leading-relaxed text-[#667085]">
        预览工作流：静态高保真 → 视觉验收（docs/13 §8）→ 集成真实 view。<br>
        生产构建自动剔除本画廊。
      </div>
    </n-layout-sider>
    <n-layout-content class="bg-[#F9FAFB] p-6">
      <router-view />
    </n-layout-content>
  </n-layout>
</template>
