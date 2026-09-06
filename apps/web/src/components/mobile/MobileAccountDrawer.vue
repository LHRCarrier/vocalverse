<script setup lang="ts">
/**
 * 账户抽屉（2026-09-05 组长拍板：底部「我的」tab 移除 → 首页顶栏头像点击弹出，X 式左侧滑出）
 * 2026-09-09 组长拍板：/m/me「我的」页面舍弃（信息收敛进抽屉）——用户卡保留，
 * 菜单 = 我的学习（→ /m/learn）+ 消息 + 设置与隐私（**抽屉内展开子项**，组长反馈 2026-09-09：
 * 点了要有子功能拉出，不能只 toast）。
 * 设置子项：帮助与反馈 / 数据与隐私 / 关于声语界（沿用 /m/me 原设置列表；演示帧 toast，M3 接真实页）。
 */
import { ref } from 'vue'
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
  { icon: 'user' as const, label: '我的学习', path: '/m/learn', expandable: false },
  { icon: 'bell' as const, label: '通知', path: '/m/notifications', expandable: false },
  { icon: 'settings' as const, label: '设置与隐私', path: null, expandable: true },
]

/* 设置子项（沿用 /m/me 原设置列表 · 演示帧；M3 接真实页面） */
const settingsChildren = [
  { icon: 'info' as const, label: '帮助与反馈' },
  { icon: 'heart' as const, label: '数据与隐私' },
  { icon: 'wave' as const, label: '关于声语界' },
]

/** 设置子面板展开态（点击主项 toggle；chevron 旋转 180°） */
const settingsOpen = ref(false)

function onItem(it: (typeof items)[number]) {
  if (it.expandable) {
    settingsOpen.value = !settingsOpen.value
    return
  }
  if (it.path) emit('navigate', it.path)
}

function onSettingsChild(label: string) {
  ui.showToast(`「${label}」M3 上线后开放`)
  settingsOpen.value = false
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
              :class="{ 'is-open': it.expandable && settingsOpen }"
              type="button"
              @click="onItem(it)"
            >
              <MobileIcon :name="it.icon" :size="18" />
              <span class="u-drawer__label">{{ it.label }}</span>
              <MobileIcon name="chevron" :size="16" class="u-drawer__go" />
            </button>

            <!-- 设置子面板（抽屉内展开 · 2026-09-09 组长反馈：要有真子功能拉出） -->
            <div v-if="settingsOpen" class="u-drawer__submenu" role="group" aria-label="设置子菜单">
              <button
                v-for="c in settingsChildren"
                :key="c.label"
                class="u-drawer__subitem"
                type="button"
                @click="onSettingsChild(c.label)"
              >
                <MobileIcon :name="c.icon" :size="16" />
                <span class="u-drawer__subitem__label">{{ c.label }}</span>
              </button>
            </div>
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
