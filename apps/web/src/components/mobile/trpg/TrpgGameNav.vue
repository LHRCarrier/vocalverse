<script setup lang="ts">
/**
 * 酒馆 · 页内底栏（设计稿 local/trpg-redesign.html 的 4 项导航）。
 *
 * 2026-09-22：/m/tavern 由全局学习组底栏改为**沉浸页 + 页内导航**（组长拍板）——
 * 大堂 / 酒馆跑团 / 角色卡 / 纪事；四项均为页内视图（页面切换内容区，本导航常驻）。
 * 离开酒馆的出口不在这里（按 docs/35 硬规则 3 固定在顶栏「离开」钮）。
 * 图标对原型（组长反馈 2026-09-22）：home / stack-2（三层紧贴）/ user / book-2，Tabler 对应源。
 */
import IconBook2 from '~icons/tabler/book-2'
import IconHome from '~icons/tabler/home'
import IconStack2 from '~icons/tabler/stack-2'
import IconUser from '~icons/tabler/user'

type NavKey = 'hall' | 'tavern' | 'card' | 'chronicle'

const props = withDefaults(defineProps<{ active?: NavKey }>(), { active: 'tavern' })

const emit = defineEmits<{ nav: [key: NavKey] }>()

const ITEMS: ReadonlyArray<{ key: NavKey; label: string; icon: typeof IconHome }> = [
  { key: 'hall', label: '大堂', icon: IconHome },
  { key: 'tavern', label: '酒馆跑团', icon: IconStack2 },
  { key: 'card', label: '角色卡', icon: IconUser },
  { key: 'chronicle', label: '纪事', icon: IconBook2 },
]
</script>

<template>
  <nav class="t-nav" aria-label="酒馆底部导航">
    <button
      v-for="item in ITEMS"
      :key="item.key"
      class="t-nav__item"
      :class="{ 't-nav__item--on': props.active === item.key }"
      type="button"
      :title="props.active === item.key ? `${item.label}（当前）` : item.label"
      :aria-label="item.label"
      :aria-current="props.active === item.key ? 'page' : undefined"
      @click="emit('nav', item.key)"
    >
      <component :is="item.icon" />
      <span>{{ item.label }}</span>
    </button>
  </nav>
</template>
