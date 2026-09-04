<script setup lang="ts">
/**
 * 移动端底部浮动 Tab 栏：首页 / 口语 / 主按钮(+ 新建会话) / 唱吧 / 我的。
 * 主按钮与「口语」同目标：+ 是显式「开始新会话」入口（页面挂载即建新会话）。
 * 退出登录在「我的」页（危险操作按钮）。
 */
import { useRoute } from 'vue-router'

import MobileIcon from './MobileIcon.vue'

const route = useRoute()
</script>

<template>
  <nav class="u-tabbar" aria-label="底部导航">
    <RouterLink to="/m/home" class="u-tab" :class="{ active: route.path === '/m/home' }">
      <MobileIcon name="home" />
      首页
    </RouterLink>
    <RouterLink to="/m/chat" class="u-tab" :class="{ active: route.path.startsWith('/m/chat') }">
      <MobileIcon name="mic" />
      口语
    </RouterLink>
    <RouterLink to="/m/chat" class="u-tab--main" title="开始新会话" aria-label="开始新会话">
      <MobileIcon name="plus" :size="26" />
    </RouterLink>
    <RouterLink to="/m/sing" class="u-tab" :class="{ active: route.path === '/m/sing' }">
      <MobileIcon name="note" />
      唱吧
    </RouterLink>
    <RouterLink to="/m/me" class="u-tab" :class="{ active: route.path === '/m/me' }">
      <MobileIcon name="user" />
      我的
    </RouterLink>
  </nav>
</template>
