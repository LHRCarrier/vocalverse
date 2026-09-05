<script setup lang="ts">
/**
 * 移动端底部 Tab 栏（2026-09-05 组长拍板：**全局挂载 App.vue**，按路由显隐）
 * 5 位对称（X 同构）：社区 / 搜索 / ＋发帖（中央第 3 位，严格居中）/ 练习 / 私信。
 * 「练习」= 场景对话 + 自由对话 + 唱吧 的合并入口（docs/14 §12 口语 Hub 思路，见 MobilePracticeView）。
 * 显隐规则（X 式）：tab 级页显示，二级页隐藏（会话/报告/我的/口语场景/自由对话/唱吧——均从 tab/抽屉进入）。
 * 图标：Tabler（unplugin-icons 编译期内联，docs/32）。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import IconHome from '~icons/tabler/home'
import IconMicrophone from '~icons/tabler/microphone'
import IconPlus from '~icons/tabler/plus'
import IconMail from '~icons/tabler/mail'
import IconSearch from '~icons/tabler/search'
import '@/styles/mobile-uic.css'

const route = useRoute()

const visible = computed(() => {
  const p = route.path
  return p === '/m/home' || p === '/m/search' || p === '/m/practice' || p === '/m/messages'
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
      to="/m/practice"
      class="u-tab"
      :class="{ active: route.path === '/m/practice' }"
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
</template>
