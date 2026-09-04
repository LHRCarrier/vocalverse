<script setup lang="ts">
/**
 * 移动端底部悬浮 Tab 栏（Soft UI 版）：首页 / 口语 / 中央主按钮(+ 新建会话) / 唱吧 / 我的。
 * 主按钮与「口语」同目标：+ 是显式「开始新会话」入口（页面挂载即建新会话）。
 * 视觉：悬浮白胶囊（float 阴影）+ safe-area；激活项 primary-soft 底 + spring 弹起；60ms 按压反馈。
 */
import { useRoute } from 'vue-router'

import MobileIcon from './MobileIcon.vue'
import '@/styles/mobile-soft.css'

const route = useRoute()
</script>

<template>
  <nav class="s-tabbar" aria-label="底部导航">
    <RouterLink to="/m/home" class="s-tab" :class="{ active: route.path === '/m/home' }">
      <MobileIcon name="home" />
      首页
    </RouterLink>
    <RouterLink to="/m/chat" class="s-tab" :class="{ active: route.path.startsWith('/m/chat') }">
      <MobileIcon name="mic" />
      口语
    </RouterLink>
    <RouterLink to="/m/chat" class="s-tab--main" title="开始新会话" aria-label="开始新会话">
      <MobileIcon name="plus" :size="26" />
    </RouterLink>
    <RouterLink to="/m/sing" class="s-tab" :class="{ active: route.path === '/m/sing' }">
      <MobileIcon name="note" />
      唱吧
    </RouterLink>
    <RouterLink to="/m/me" class="s-tab" :class="{ active: route.path === '/m/me' }">
      <MobileIcon name="user" />
      我的
    </RouterLink>
  </nav>
</template>
