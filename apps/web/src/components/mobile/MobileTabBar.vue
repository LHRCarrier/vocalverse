<script setup lang="ts">
/**
 * 移动端底部 Tab 栏（2026-09-05 组长拍板 4：**全局挂载 App.vue**，按路由显隐）
 * 6 位：社区 / 搜索 / ＋发帖（中央主行动）/ 口语 / 唱吧 / 私信。
 * 显隐规则（X 式）：tab 级页显示（home/search/chat/sing/messages），二级页隐藏
 * （会话 messages/:id、报告、我的、自由对话——X 的二级页同样无底部栏）。
 * 图标：Tabler（unplugin-icons 编译期内联，docs/32）。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import IconHome from '~icons/tabler/home'
import IconMicrophone from '~icons/tabler/microphone'
import IconMusic from '~icons/tabler/music'
import IconPlus from '~icons/tabler/plus'
import IconMail from '~icons/tabler/mail'
import IconSearch from '~icons/tabler/search'
import '@/styles/mobile-uic.css'

const route = useRoute()

const visible = computed(() => {
  const p = route.path
  return (
    p === '/m/home' ||
    p === '/m/search' ||
    p.startsWith('/m/chat') || // 口语（含 /m/chat/:sceneId 直入）
    p === '/m/sing' ||
    p === '/m/messages'
  )
})
</script>

<template>
  <nav v-if="visible" class="u-tabbar" aria-label="底部导航">
    <RouterLink to="/m/home" class="u-tab" :class="{ active: route.path === '/m/home' }" title="社区" aria-label="社区">
      <IconHome />
    </RouterLink>
    <RouterLink
      to="/m/search"
      class="u-tab"
      :class="{ active: route.path === '/m/search' }"
      title="搜索"
      aria-label="搜索"
    >
      <IconSearch />
    </RouterLink>
    <RouterLink to="/m/compose" class="u-tab--main" title="发帖" aria-label="发帖">
      <IconPlus />
    </RouterLink>
    <RouterLink
      to="/m/chat"
      class="u-tab"
      :class="{ active: route.path.startsWith('/m/chat') }"
      title="口语"
      aria-label="口语"
    >
      <IconMicrophone />
    </RouterLink>
    <RouterLink to="/m/sing" class="u-tab" :class="{ active: route.path === '/m/sing' }" title="唱吧" aria-label="唱吧">
      <IconMusic />
    </RouterLink>
    <RouterLink
      to="/m/messages"
      class="u-tab"
      :class="{ active: route.path === '/m/messages' }"
      title="私信"
      aria-label="私信"
    >
      <IconMail />
    </RouterLink>
  </nav>
</template>
