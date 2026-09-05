<script setup lang="ts">
/**
 * 移动端底部 Tab 栏（2026-09-05 组长拍板 7：**双场景分组，全局挂载 App.vue**）
 * 社区场景一组 tab、练习场景一组 tab；各场景功能直接上底栏，彼此以出口图标互切：
 * - 社区组（/m/home 等）：🏠 社区 / 🔍 搜索 / ＋发帖(中央) / 🎤 练习(出口) / ✉️ 私信
 * - 练习组（/m/practice 等）：🏠 Home(出口) / ☕ 场景对话 / 🎤 开始练习(中央) / 🎵 唱吧 / 💬 自由对话
 * 场景归属：社区 = home/search/messages(含会话)/me/report；练习 = practice/chat(含场景)/free-chat/sing；
 * 沉浸页 compose 无底部栏。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import IconCoffee from '~icons/tabler/coffee'
import IconHome from '~icons/tabler/home'
import IconMail from '~icons/tabler/mail'
import IconMessageCircle from '~icons/tabler/message-circle'
import IconMicrophone from '~icons/tabler/microphone'
import IconMusic from '~icons/tabler/music'
import IconPlus from '~icons/tabler/plus'
import IconSearch from '~icons/tabler/search'
import '@/styles/mobile-uic.css'

const route = useRoute()

const group = computed<null | 'community' | 'practice'>(() => {
  const p = route.path
  if (p === '/m/home' || p === '/m/search' || p === '/m/me' || p === '/m/report' || p.startsWith('/m/messages')) {
    return 'community'
  }
  if (p === '/m/practice' || p.startsWith('/m/chat') || p === '/m/free-chat' || p === '/m/sing') {
    return 'practice'
  }
  return null // /m/compose 沉浸页
})
</script>

<template>
  <!-- 社区场景组 -->
  <nav v-if="group === 'community'" class="u-tabbar" aria-label="社区底部导航">
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
      to="/m/practice"
      class="u-tab"
      :class="{ active: false }"
      title="练习"
      aria-label="练习"
    >
      <IconMicrophone />
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

  <!-- 练习场景组 -->
  <nav v-else-if="group === 'practice'" class="u-tabbar" aria-label="练习底部导航">
    <RouterLink to="/m/home" class="u-tab" :class="{ active: false }" title="返回社区" aria-label="返回社区">
      <IconHome />
    </RouterLink>
    <RouterLink
      to="/m/chat"
      class="u-tab"
      :class="{ active: route.path.startsWith('/m/chat') }"
      title="场景对话"
      aria-label="场景对话"
    >
      <IconCoffee />
    </RouterLink>
    <RouterLink to="/m/chat" class="u-tab--main" title="开始练习" aria-label="开始练习">
      <IconMicrophone />
    </RouterLink>
    <RouterLink
      to="/m/sing"
      class="u-tab"
      :class="{ active: route.path === '/m/sing' }"
      title="唱吧"
      aria-label="唱吧"
    >
      <IconMusic />
    </RouterLink>
    <RouterLink
      to="/m/free-chat"
      class="u-tab"
      :class="{ active: route.path === '/m/free-chat' }"
      title="自由对话"
      aria-label="自由对话"
    >
      <IconMessageCircle />
    </RouterLink>
  </nav>
</template>
