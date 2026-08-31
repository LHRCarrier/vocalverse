<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { NButton, NLayout, NLayoutContent, NLayoutSider, NMenu, NSelect, NTag } from 'naive-ui'
import { RouterLink, useRoute } from 'vue-router'

import type { MenuOption } from 'naive-ui'

import AdminLayout from '@/layouts/AdminLayout.vue'
import UserLayout from '@/layouts/UserLayout.vue'

import { previewPages } from './registry'

type PreviewMode = 'gallery' | 'user' | 'admin'

const route = useRoute()

/**
 * 布局模拟模式（docs/13 §8 盲点修正）：
 * - 默认 = 当前预览页登记的 layout（用户端页→UserLayout、管理端页→AdminLayout），
 *   保证"所见即生产"（TopNav/侧边栏与集成后一致）；
 * - 可手动切换任意模式对比；切页时按登记值重置。
 */
const mode = ref<PreviewMode>('gallery')

watch(
  () => route.path,
  (path) => {
    const page = previewPages.find((p) => p.path === path)
    mode.value = page?.layout ?? 'gallery'
  },
  { immediate: true },
)

const activeKey = computed(() => String(route.path))

const groups = ['用户端', '管理端'] as const

const modeOptions = [
  { label: '画廊模式', value: 'gallery' },
  { label: '用户端布局', value: 'user' },
  { label: '管理端布局', value: 'admin' },
]

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
  <!-- 布局模拟：以真实布局包裹预览页（所见即生产） -->
  <template v-if="mode !== 'gallery'">
    <UserLayout v-if="mode === 'user'" />
    <AdminLayout v-else />
    <div class="fixed right-4 top-4 z-50 flex items-center gap-2">
      <NSelect
        v-model:value="mode"
        size="small"
        :options="modeOptions"
        class="w-[150px]"
        @update:value="mode = $event"
      />
      <NButton size="small" type="primary" secondary @click="mode = 'gallery'">返回画廊</NButton>
    </div>
  </template>

  <!-- 画廊模式：左侧目录 + 内容区 + 模式切换 -->
  <n-layout v-else class="min-h-screen" has-sider>
    <n-layout-sider bordered :width="240" content-class="flex flex-col">
      <div class="flex items-center gap-2 px-4 py-3">
        <span class="inline-block h-3 w-3 rounded-full bg-accent" />
        <span class="font-bold">前端预览画廊</span>
        <NTag size="small" type="warning">DEV ONLY</NTag>
      </div>
      <n-menu :value="activeKey" :options="renderMenu()" />
      <div class="mt-auto border-t border-[#E5E7EB] px-4 py-3 text-xs leading-relaxed text-[#667085]">
        预览工作流：静态高保真 → 视觉验收（docs/13 §8）→ 集成真实 view 后<b>删除本页</b>。<br>
        生产构建自动剔除本画廊（零残留），无需上线操作。右上角可切"真实布局"模式（所见即生产）。
      </div>
    </n-layout-sider>
    <n-layout-content class="bg-[#F9FAFB] p-6">
      <router-view />
    </n-layout-content>
  </n-layout>
</template>
