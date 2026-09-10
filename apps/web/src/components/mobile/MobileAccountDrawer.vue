<script setup lang="ts">
/**
 * 账户抽屉（2026-09-05 组长拍板：底部「我的」tab 移除 → 首页顶栏头像点击弹出，X 式左侧滑出）
 * 2026-09-09 组长拍板：/m/me「我的」页面舍弃（信息收敛进抽屉）——用户卡保留，菜单：
 *   ① 我的学习（**抽屉内展开四个模块**：单词/社区足迹/发音/练习 → /m/learn/:module，组长反馈 2026-09-09 v2）
 *   ② 通知（→ /m/notifications 通知中心）
 *   ③ 设置与隐私（抽屉内展开子项：帮助与反馈/数据与隐私/关于声语界，演示帧 toast，M3 接真实页）
 * 展开项右侧 chevron 在展开时旋转 180°（下拉指示与功能一致）。
 */
import { reactive } from 'vue'
import MobileAvatar from '@/components/mobile/MobileAvatar.vue'
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

interface MenuChild {
  icon: 'book' | 'heart' | 'mic' | 'flame' | 'info' | 'wave' | 'mail' | 'bell' | 'user-plus' | 'hash'
  label: string
  path: string | null
}

interface MenuItem {
  icon: 'user' | 'bell' | 'settings' | 'mail'
  label: string
  path: string | null
  children?: MenuChild[]
}

const items: MenuItem[] = [
  {
    icon: 'user',
    label: '我的学习',
    path: null,
    children: [
      { icon: 'book', label: '我的单词', path: '/m/learn/words' },
      { icon: 'hash', label: '社区足迹', path: '/m/me/posts' },
      { icon: 'mic', label: '我的发音', path: '/m/learn/speaking' },
      { icon: 'flame', label: '练习情况', path: '/m/learn/practice' },
    ],
  },
  {
    icon: 'bell',
    label: '通知',
    path: null,
    children: [
      { icon: 'mail', label: '私信', path: '/m/notifications?tab=msg' },
      { icon: 'bell', label: '互动通知', path: '/m/notifications?tab=notice' },
      { icon: 'user-plus', label: '关注动态', path: '/m/notifications?tab=follow' },
    ],
  },
  {
    icon: 'settings',
    label: '设置与隐私',
    path: null,
    children: [
      { icon: 'info', label: '帮助与反馈', path: null },
      { icon: 'heart', label: '数据与隐私', path: null },
      { icon: 'wave', label: '关于声语界', path: null },
    ],
  },
]

/** 各项展开态（独立 toggle · 2026-09-09：我的学习四模块 / 设置子项） */
const opens = reactive<Record<string, boolean>>({})

function toggle(key: string) {
  opens[key] = !opens[key]
}

function go(item: MenuItem, child?: MenuChild) {
  const path = child?.path ?? item.path
  if (path) {
    emit('navigate', path)
    opens[item.label] = false // 子项点击后收起面板
    return
  }
  ui.showToast(`「${child?.label ?? item.label}」M3 上线后开放`)
  opens[item.label] = false
}
</script>

<template>
  <Teleport to="body">
    <Transition name="u-drawer">
      <div v-if="props.open" class="u-drawer-mask" @click.self="emit('update:open', false)">
        <aside class="u-drawer" role="dialog" aria-label="账户菜单" @keydown.esc="emit('update:open', false)">
          <!-- 用户卡 -->
          <header class="u-drawer__head">
            <MobileAvatar
              :src="props.me?.avatarUrl"
              :name="props.me?.nickname ?? props.me?.username"
              :tint="props.me?.tint"
              size="md"
            />
            <span class="u-drawer__who">
              <strong class="u-drawer__name">{{ props.me?.nickname ?? props.me?.username ?? '同学' }}</strong>
              <span class="u-drawer__sub">
                {{ props.me ? `@${props.me.handle ?? props.me.username} · ${progress.lvLabel}` : '未登录' }}
              </span>
            </span>
            <button
              class="u-drawer__edit"
              type="button"
              title="编辑资料"
              aria-label="编辑资料"
              @click="emit('navigate', '/m/me/profile')"
            >
              <MobileIcon name="settings" :size="16" />
            </button>
          </header>

          <!-- 菜单 -->
          <nav class="u-drawer__menu" aria-label="账户菜单项">
            <template v-for="it in items" :key="it.label">
              <button
                class="u-drawer__item"
                :class="{ 'is-open': it.children && opens[it.label] }"
                type="button"
                @click="it.children ? toggle(it.label) : go(it)"
              >
                <MobileIcon :name="it.icon" :size="18" />
                <span class="u-drawer__label">{{ it.label }}</span>
                <MobileIcon name="chevron" :size="16" class="u-drawer__go" />
              </button>

              <!-- 子面板（抽屉内展开 · 我的学习四模块 / 设置子项） -->
              <div v-if="it.children && opens[it.label]" class="u-drawer__submenu" role="group" :aria-label="`${it.label}子菜单`">
                <button
                  v-for="c in it.children"
                  :key="c.label"
                  class="u-drawer__subitem"
                  type="button"
                  @click="go(it, c)"
                >
                  <MobileIcon :name="c.icon" :size="16" />
                  <span class="u-drawer__subitem__label">{{ c.label }}</span>
                </button>
              </div>
            </template>
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
