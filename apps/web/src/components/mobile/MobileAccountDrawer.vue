<script setup lang="ts">
/**
 * 账户抽屉（2026-09-05 组长拍板：底部「我的」tab 移除 → 首页顶栏头像点击弹出，X 式左侧滑出）
 * 2026-09-09 组长拍板：/m/me「我的」页面舍弃（信息收敛进抽屉）——用户卡保留，
 * 菜单 = 我的学习（→ /m/learn）+ 消息 + 设置与隐私（演示帧 toast，M3 接真实设置页）。
 * 菜单项 emit navigate(path)，退出 emit logout——由挂载页接（路由跳转 + auth 清理）。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { useProgressStore } from '@/stores/progress'
import { useUiStore } from '@/stores/ui'

import type { MeView } from '@/stores/auth'

const progress = useProgressStore()
const ui = useUiStore()

const props = defineProps<{
  open: boolean
  me: MeView | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  navigate: [path: string]
  logout: []
}>()

const items = [
  { icon: 'user' as const, label: '我的学习', path: '/m/learn' },
  { icon: 'mail' as const, label: '消息', path: '/m/messages' },
  { icon: 'settings' as const, label: '设置与隐私', path: null },
]

function onItem(it: (typeof items)[number]) {
  if (it.path) emit('navigate', it.path)
  else ui.showToast('「设置与隐私」M3 上线后开放')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="u-drawer">
      <div v-if="props.open" class="u-drawer-mask" @click.self="emit('update:open', false)">
        <aside class="u-drawer" role="dialog" aria-label="账户菜单" @keydown.esc="emit('update:open', false)">
          <!-- 用户卡 -->
          <header class="u-drawer__head">
            <span class="u-drawer__ava">{{ (props.me?.nickname ?? props.me?.username ?? '同').slice(0, 1).toUpperCase() }}</span>
            <span class="u-drawer__who">
              <strong class="u-drawer__name">{{ props.me?.nickname ?? props.me?.username ?? '同学' }}</strong>
              <span class="u-drawer__sub">
                {{ props.me ? `@${props.me.username} · ${progress.lvLabel}` : '未登录' }}
              </span>
            </span>
          </header>

          <!-- 菜单 -->
          <nav class="u-drawer__menu" aria-label="账户菜单项">
            <button
              v-for="it in items"
              :key="it.label"
              class="u-drawer__item"
              type="button"
              @click="onItem(it)"
            >
              <MobileIcon :name="it.icon" :size="18" />
              <span class="u-drawer__label">{{ it.label }}</span>
              <MobileIcon name="chevron" :size="16" class="u-drawer__go" />
            </button>
          </nav>

          <!-- 危险区：退出登录 -->
          <footer class="u-drawer__foot">
            <button class="u-drawer__logout" type="button" @click="emit('logout')">
              <MobileIcon name="logout" :size="18" />
              退出登录
            </button>
          </footer>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>
