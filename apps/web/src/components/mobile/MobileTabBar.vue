<script setup lang="ts">
/**
 * 移动端底部悬浮 Tab 栏（v3.1）：首页 / 口语 / 中央主按钮(+ 新建会话) / 唱吧 / 我的。
 * 视觉：悬浮白胶囊 + safe-area；激活 primary-soft 底 + 图标 spring 弹起；60ms 按压反馈。
 * 图标：Tabler（unplugin-icons 编译期内联，docs/32）。
 */
import { useRoute } from 'vue-router'

import IconHome from '~icons/tabler/home'
import IconMicrophone from '~icons/tabler/microphone'
import IconMusic from '~icons/tabler/music'
import IconPlus from '~icons/tabler/plus'
import IconUser from '~icons/tabler/user'
import '@/styles/mobile-soft.css'

const route = useRoute()
</script>

<template>
  <nav class="s-tabbar" aria-label="底部导航">
    <RouterLink to="/m/home" class="s-tab" :class="{ active: route.path === '/m/home' }">
      <IconHome />
      首页
    </RouterLink>
    <RouterLink to="/m/chat" class="s-tab" :class="{ active: route.path.startsWith('/m/chat') }">
      <IconMicrophone />
      口语
    </RouterLink>
    <RouterLink to="/m/chat" class="s-tab--main" title="开始新会话" aria-label="开始新会话">
      <IconPlus />
    </RouterLink>
    <RouterLink to="/m/sing" class="s-tab" :class="{ active: route.path === '/m/sing' }">
      <IconMusic />
      唱吧
    </RouterLink>
    <RouterLink to="/m/me" class="s-tab" :class="{ active: route.path === '/m/me' }">
      <IconUser />
      我的
    </RouterLink>
  </nav>
</template>
