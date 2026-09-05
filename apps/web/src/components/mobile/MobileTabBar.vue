<script setup lang="ts">
/**
 * 移动端底部悬浮 Tab 栏（2026-09-05 组长拍板：换用口语同款 uic 新样式——浮卡圆角 + 炭黑中央主钮）
 * 功能不变：首页（社区）/ 口语 / 中央主按钮(+ 新建 / 进口语) / 唱吧 / 我的。
 * 图标：Tabler（unplugin-icons 编译期内联，docs/32）。
 */
import { useRoute } from 'vue-router'

import IconHome from '~icons/tabler/home'
import IconMicrophone from '~icons/tabler/microphone'
import IconMusic from '~icons/tabler/music'
import IconPlus from '~icons/tabler/plus'
import IconUser from '~icons/tabler/user'
import '@/styles/mobile-uic.css'

const route = useRoute()
</script>

<template>
  <nav class="u-tabbar" aria-label="底部导航">
    <RouterLink to="/m/home" class="u-tab" :class="{ active: route.path === '/m/home' }" title="社区" aria-label="社区">
      <IconHome />
    </RouterLink>
    <RouterLink
      to="/m/chat"
      class="u-tab"
      :class="{ active: route.path.startsWith('/m/chat') || route.path.startsWith('/m/free-chat') }"
      title="口语"
      aria-label="口语"
    >
      <IconMicrophone />
    </RouterLink>
    <RouterLink to="/m/chat" class="u-tab--main" title="开始新会话" aria-label="开始新会话">
      <IconPlus />
    </RouterLink>
    <RouterLink to="/m/sing" class="u-tab" :class="{ active: route.path === '/m/sing' }" title="唱吧" aria-label="唱吧">
      <IconMusic />
    </RouterLink>
    <RouterLink to="/m/me" class="u-tab" :class="{ active: route.path === '/m/me' }" title="我的" aria-label="我的">
      <IconUser />
    </RouterLink>
  </nav>
</template>
