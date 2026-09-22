<script setup lang="ts">
/**
 * 酒馆 · 页内底栏（设计稿 local/trpg-redesign.html 的 4 项导航）。
 *
 * 2026-09-22：/m/tavern 由全局学习组底栏改为**沉浸页 + 页内导航**（组长拍板）——
 * 大堂 / 酒馆跑团 / 角色卡 / 纪事；仅「酒馆跑团」为当前场景，
 * 其余三项为**占位**：点击上抛 key，由页面用全局 toast 提示后续版本开放。
 * 离开酒馆的出口不在这里（按 docs/35 硬规则 3 固定在顶栏「离开」钮）。
 * 图标对原型（组长反馈 2026-09-22）：home / stack-2（三层紧贴）/ user / book-2，Tabler 对应源。
 */
import IconBook2 from '~icons/tabler/book-2'
import IconHome from '~icons/tabler/home'
import IconStack2 from '~icons/tabler/stack-2'
import IconUser from '~icons/tabler/user'

const emit = defineEmits<{ nav: [key: 'hall' | 'tavern' | 'card' | 'chronicle'] }>()
</script>

<template>
  <nav class="t-nav" aria-label="酒馆底部导航">
    <button
      class="t-nav__item"
      type="button"
      title="大堂"
      aria-label="大堂"
      @click="emit('nav', 'hall')"
    >
      <IconHome />
      <span>大堂</span>
    </button>
    <button
      class="t-nav__item t-nav__item--on"
      type="button"
      title="酒馆跑团（当前）"
      aria-label="酒馆跑团"
      @click="emit('nav', 'tavern')"
    >
      <IconStack2 />
      <span>酒馆跑团</span>
    </button>
    <button
      class="t-nav__item"
      type="button"
      title="角色卡"
      aria-label="角色卡"
      @click="emit('nav', 'card')"
    >
      <IconUser />
      <span>角色卡</span>
    </button>
    <button
      class="t-nav__item"
      type="button"
      title="纪事"
      aria-label="纪事"
      @click="emit('nav', 'chronicle')"
    >
      <IconBook2 />
      <span>纪事</span>
    </button>
  </nav>
</template>
