<script setup lang="ts">
/**
 * 侧栏（docs/50 §11.3）。
 *
 * 从 `ConsoleLayout.vue` 拆出来，有两个非"为了过行数限制"的理由：
 * 1. 导航裁剪逻辑（按权限过滤 + 分组隐藏）是独立可测的单元；
 * 2. 布局外壳因此只剩"排布"一件事，改导航不会动到布局。
 */
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import IconLayoutSidebar from '~icons/tabler/layout-sidebar'
import IconMenu2 from '~icons/tabler/menu-2'

import NavIcon from '@/components/layout/NavIcon.vue'
import { NAV_GROUPS } from '@/router/nav'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()

const collapsed = ref(false)

/** 分组内一个菜单项都没有 → 整个分组不显示（否则会出现只有标题的空组） */
const groups = computed(() =>
  NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => {
      if (!item.permission) return true
      return item.anyOf ? auth.hasAny(item.permission) : auth.hasPermission(item.permission)
    }),
  })).filter((group) => group.items.length > 0),
)

function isActive(path: string): boolean {
  if (path === '/') return route.path === '/'
  // 详情页归属到列表项（/ops/traces/abc → /ops/traces）
  return route.path === path || route.path.startsWith(`${path}/`)
}
</script>

<template>
  <aside class="c-sider" :class="{ 'c-sider--collapsed': collapsed }">
    <div class="c-brand">
      <span class="c-brand-mark">VV</span>
      <div v-if="!collapsed" class="c-brand-text">
        <span class="c-brand-name">VocalVerse 控制台</span>
        <span class="c-brand-sub">CONSOLE</span>
      </div>
    </div>

    <nav class="c-nav">
      <div v-for="group in groups" :key="group.key" class="c-nav-group">
        <div v-if="!collapsed" class="c-nav-group-label">{{ group.label }}</div>
        <hr v-else class="c-nav-group-rule">
        <RouterLink
          v-for="item in group.items"
          :key="item.path"
          :to="item.path"
          class="c-nav-item"
          :class="{ 'c-nav-item--active': isActive(item.path) }"
          :title="collapsed ? item.label : undefined"
        >
          <span class="c-nav-icon" aria-hidden="true">
            <NavIcon :name="item.icon" :size="18" />
          </span>
          <span v-if="!collapsed" class="c-nav-label">{{ item.label }}</span>
        </RouterLink>
      </div>
    </nav>

    <button
      class="c-collapse"
      type="button"
      :title="collapsed ? '展开侧栏' : '折叠侧栏'"
      :aria-label="collapsed ? '展开侧栏' : '折叠侧栏'"
      :aria-expanded="!collapsed"
      @click="collapsed = !collapsed"
    >
      <IconLayoutSidebar v-if="!collapsed" width="16" height="16" aria-hidden="true" />
      <IconMenu2 v-else width="16" height="16" aria-hidden="true" />
    </button>
  </aside>
</template>

<style scoped>
.c-sider {
  display: flex;
  flex-direction: column;
  flex: 0 0 var(--layout-sider);
  width: var(--layout-sider);
  background: var(--c-surface);
  border-right: 1px solid var(--c-border);
  transition: flex-basis var(--vv-t-std) var(--vv-ease-out), width var(--vv-t-std) var(--vv-ease-out);
}
.c-sider--collapsed {
  flex-basis: var(--layout-sider-collapsed);
  width: var(--layout-sider-collapsed);
}
.c-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: var(--layout-header);
  padding: 0 16px;
  flex: 0 0 auto;
}
.c-brand-mark {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--c-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
  flex: 0 0 auto;
}
.c-brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.c-brand-name {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}
.c-brand-sub {
  font-size: 10px;
  letter-spacing: 0.14em;
  color: var(--c-text-3);
}
.c-nav {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 4px 10px 16px;
}
.c-nav-group + .c-nav-group {
  margin-top: 10px;
}
.c-nav-group-label {
  padding: 8px 8px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--c-text-3);
}
.c-nav-group-rule {
  height: 1px;
  border: 0;
  background: var(--c-border);
  margin: 8px 4px;
}
.c-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 10px;
  border-radius: var(--c-ctl-radius);
  color: var(--c-text-2);
  font-size: 13px;
  transition: background var(--vv-t-micro) var(--vv-ease-out), color var(--vv-t-micro) var(--vv-ease-out);
}
.c-nav-item:hover {
  background: var(--c-surface-sunken);
  color: var(--c-text);
}
.c-nav-item--active {
  background: var(--c-primary-soft);
  color: var(--c-primary);
  font-weight: 500;
}
.c-nav-icon {
  display: grid;
  place-items: center;
  flex: 0 0 18px;
  line-height: 0;
}
.c-nav-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.c-collapse {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  height: 40px;
  margin: 0 10px 10px;
  border: 1px solid var(--c-border);
  border-radius: var(--c-ctl-radius);
  background: transparent;
  color: var(--c-text-2);
  cursor: pointer;
  transition: background var(--vv-t-micro) var(--vv-ease-out);
}
.c-collapse:hover {
  background: var(--c-surface-sunken);
}
</style>
