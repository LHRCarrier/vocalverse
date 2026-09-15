<script setup lang="ts">
/**
 * 顶栏（docs/50 §11.3）。
 *
 * 只放四件事：面包屑 / 未处理预警角标 / 当前角色徽标 / 账号菜单。
 * 刻意不放全局搜索——控制台的数据是分域的，跨域全局搜索在权限模型下
 * 要么漏结果要么越权，先不做（docs/50 §15.1 范围裁定）。
 */
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NDropdown, useDialog } from 'naive-ui'
import type { DropdownOption } from 'naive-ui'
import IconBell from '~icons/tabler/bell'
import IconChevronDown from '~icons/tabler/chevron-down'
import IconLogout from '~icons/tabler/logout'
import IconUserCircle from '~icons/tabler/user-circle'

import { ROLE_LABEL } from '@/router/nav'
import { useAlertStore } from '@/stores/alerts'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const alerts = useAlertStore()
const dialog = useDialog()

const currentTitle = computed(() => (route.meta.title as string | undefined) ?? '工作台')
const roleMeta = computed(() => ROLE_LABEL[auth.roleCode] ?? { name: auth.roleCode || '—', tone: 'muted' as const })
const canSeeAlerts = computed(() => auth.hasPermission('ops:alert:read'))

onMounted(() => {
  // 只有具备预警读权限的账号才轮询——无权限的账号没必要打这个接口
  if (canSeeAlerts.value) alerts.start()
})
onBeforeUnmount(() => alerts.stop())

const options: DropdownOption[] = [{ label: '退出登录', key: 'logout' }]

function onSelect(key: string): void {
  if (key !== 'logout') return
  dialog.warning({
    title: '退出登录',
    content: '退出后需要重新输入账号口令。',
    positiveText: '退出',
    negativeText: '取消',
    onPositiveClick: async () => {
      await auth.logout()
      await router.push('/login')
    },
  })
}
</script>

<template>
  <header class="c-header">
    <div class="c-crumb">
      <span class="c-crumb-root">控制台</span>
      <span class="c-crumb-sep">/</span>
      <span class="c-crumb-current">{{ currentTitle }}</span>
    </div>

    <div class="c-header-actions">
      <RouterLink
        v-if="canSeeAlerts"
        to="/ops/alerts"
        class="c-bell"
        :title="alerts.firing > 0 ? `${alerts.firing} 条预警未处理` : '无未处理预警'"
        :aria-label="alerts.firing > 0 ? `${alerts.firing} 条预警未处理` : '无未处理预警'"
      >
        <IconBell width="18" height="18" aria-hidden="true" />
        <span v-if="alerts.firing > 0" class="c-bell-dot c-num">
          {{ alerts.firing > 99 ? '99+' : alerts.firing }}
        </span>
      </RouterLink>

      <span class="c-badge" :class="`c-badge--${roleMeta.tone}`" :title="`角色 ${auth.roleCode}`">
        {{ roleMeta.name }}
      </span>

      <n-dropdown :options="options" trigger="click" @select="onSelect">
        <button class="c-account" type="button">
          <IconUserCircle width="18" height="18" aria-hidden="true" />
          <span class="c-account-name">{{ auth.profile?.displayName ?? '' }}</span>
          <IconChevronDown width="14" height="14" aria-hidden="true" />
        </button>
      </n-dropdown>

      <button
        class="c-icon-btn"
        type="button"
        title="退出登录"
        aria-label="退出登录"
        @click="onSelect('logout')"
      >
        <IconLogout width="16" height="16" style="transform: scaleX(-1)" aria-hidden="true" />
      </button>
    </div>
  </header>
</template>

<style scoped>
.c-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: var(--layout-header);
  flex: 0 0 auto;
  padding: 0 20px;
  background: color-mix(in srgb, var(--c-bg) 82%, transparent);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--c-border);
}
.c-crumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  min-width: 0;
}
.c-crumb-root,
.c-crumb-sep {
  color: var(--c-text-3);
}
.c-crumb-current {
  font-weight: 600;
}
.c-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.c-bell {
  position: relative;
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--c-ctl-radius);
  color: var(--c-text-2);
  transition: background var(--vv-t-micro) var(--vv-ease-out);
}
.c-bell:hover {
  background: var(--c-surface-sunken);
  color: var(--c-text);
}
.c-bell-dot {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: var(--vv-r-pill);
  background: var(--c-danger);
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  line-height: 16px;
  text-align: center;
}
.c-account {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--c-border);
  border-radius: var(--vv-r-pill);
  background: transparent;
  color: var(--c-text-2);
  font-size: 13px;
  cursor: pointer;
  transition: background var(--vv-t-micro) var(--vv-ease-out);
}
.c-account:hover {
  background: var(--c-surface-sunken);
}
.c-account-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.c-icon-btn {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: var(--c-ctl-radius);
  background: transparent;
  color: var(--c-text-2);
  cursor: pointer;
  transition: background var(--vv-t-micro) var(--vv-ease-out);
}
.c-icon-btn:hover {
  background: var(--c-surface-sunken);
  color: var(--c-danger);
}
</style>
