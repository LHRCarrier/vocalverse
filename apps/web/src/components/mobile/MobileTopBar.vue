<script setup lang="ts">
/**
 * 移动端统一顶栏（2026-09-05 组长拍板：全局头像 + 页面标题 + 右侧功能扩展按钮；
 * 2026-09-09 组长反馈调整：离开钮从左侧移到右侧 actions 末尾——X 范式「左侧=身份入口，
 * 右侧=操作」，头像左一更干净；明确回口保留（系统返回手势在 WebView 壳/历史栈中不可靠））
 * 左 = 全局头像（点击开账户抽屉，App.vue 全局挂载）；
 * 中 = 页面标题（X 式居中）；右侧 = actions 插槽（按页面功能放按钮）+ 离开钮（可选）。
 */
import { computed } from 'vue'
import IconLogout from '~icons/tabler/logout'

import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const props = withDefaults(
  defineProps<{
    title: string
    back?: boolean
  }>(),
  { back: false },
)

const emit = defineEmits<{
  back: []
}>()

const auth = useAuthStore()
const ui = useUiStore()

const avatarLetter = computed(() => (auth.me?.nickname ?? auth.me?.username ?? '同').slice(0, 1).toUpperCase())
</script>

<template>
  <header class="u-topbar">
    <div class="u-topbar__left">
      <!-- 头像固定最左侧（组长定规：左侧不可有其他图标） -->
      <button class="u-topbar__ava" type="button" title="账户菜单" aria-label="账户菜单" @click="ui.openDrawer()">
        {{ avatarLetter }}
      </button>
    </div>
    <h1 class="u-topbar__title">{{ props.title }}</h1>
    <div class="u-topbar__acts">
      <slot name="actions" />
      <!-- 离开钮 = tabler logout 镜像（门+箭头朝左）；右侧规格 20px + 44px 触控 -->
      <button v-if="props.back" class="u-topbar__act u-topbar__back" type="button" title="离开" aria-label="离开" @click="emit('back')">
        <IconLogout />
      </button>
    </div>
  </header>
</template>
