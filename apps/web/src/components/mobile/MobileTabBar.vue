<script setup lang="ts">
/**
 * 移动端底部 Tab 栏（2026-09-05 组长拍板 7：**双场景分组，全局挂载 App.vue**）
 * 社区场景一组 tab、学习场景一组 tab；各场景功能直接上底栏，彼此以出口图标互切：
 * - 社区组（/m/home 等）：🏠 社区 / 🔍 搜索 / ＋发帖(中央) / 📚 学习(出口) / ✉️ 私信
 * - 学习组（/m/learn 等）：🏠 Home(出口) / 🍺 酒馆(中央) / 📖 笔记 / 🎵 唱吧 / 💬 自由对话
 * 场景归属：社区 = home/search/notifications(含会话)/report；学习 = learn(含 :module 详情)/notes/tavern/free-chat/sing；
 * 沉浸页 compose 无底部栏。2026-09-05 晚 8：练习 → 学习更名（路由 /m/learn）；09-09 /m/me 舍弃（收敛进抽屉）；
 * 私信收敛进通知中心。2026-09-21：场景对话 /m/chat → 酒馆 /m/tavern（ai4u TRPG 迁移，docs/52）。
 */
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'

import IconBeer from '~icons/tabler/beer'
import IconBell from '~icons/tabler/bell'
import IconBook from '~icons/tabler/book'
import IconHome from '~icons/tabler/home'
import IconMessageCircle from '~icons/tabler/message-circle'
import IconMicrophone from '~icons/tabler/microphone'
import IconMusic from '~icons/tabler/music'
import IconPlus from '~icons/tabler/plus'
import IconSearch from '~icons/tabler/search'

import MobileUnreadBadge from '@/components/mobile/MobileUnreadBadge.vue'
import { useMessagesStore } from '@/stores/messages'
import '@/styles/mobile-uic.css'

const route = useRoute()
const messages = useMessagesStore()

/* 未读角标（docs/49 §4.1 ② 的落地）：进入/切换页面时对齐一次全局未读（节流在 store 内） */
onMounted(() => void messages.loadUnreadTotal())
watch(
  () => route.path,
  () => void messages.loadUnreadTotal(),
)

const group = computed<null | 'community' | 'learn'>(() => {
  const p = route.path
  if (
    p === '/m/home' ||
    p === '/m/search' ||
    p === '/m/report' ||
    p === '/m/notifications' ||
    p.startsWith('/m/messages')
  ) {
    return 'community'
  }
  if (
    p === '/m/learn' ||
    p.startsWith('/m/learn/') ||
    p === '/m/checkin' ||
    p === '/m/notes' ||
    p === '/m/tavern' ||
    p === '/m/free-chat' ||
    p === '/m/sing' ||
    /* 读书域（docs/45 §6）：书架/书详情/生词本属学习组；阅读器保持沉浸（null） */
    p === '/m/bookshelf' ||
    p.startsWith('/m/books/') ||
    p === '/m/vocab'
  ) {
    return 'learn'
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
      to="/m/learn"
      class="u-tab"
      :class="{ active: false }"
      title="学习"
      aria-label="学习"
    >
      <IconMicrophone />
    </RouterLink>
    <RouterLink
      to="/m/notifications"
      class="u-tab"
      :class="{ active: route.path === '/m/notifications' }"
      title="通知"
      aria-label="通知"
    >
      <IconBell />
      <MobileUnreadBadge :count="messages.unreadTotal" />
    </RouterLink>
  </nav>

  <!-- 学习场景组 -->
  <nav v-else-if="group === 'learn'" class="u-tabbar" aria-label="学习底部导航">
    <RouterLink to="/m/home" class="u-tab" :class="{ active: false }" title="返回社区" aria-label="返回社区">
      <IconHome />
    </RouterLink>
    <RouterLink
      to="/m/tavern"
      class="u-tab"
      :class="{ active: route.path === '/m/tavern' }"
      title="酒馆"
      aria-label="酒馆"
    >
      <IconBeer />
    </RouterLink>
    <RouterLink to="/m/notes" class="u-tab--main" title="笔记" aria-label="笔记">
      <IconBook />
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
