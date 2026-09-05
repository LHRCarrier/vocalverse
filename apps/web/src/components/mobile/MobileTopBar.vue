<script setup lang="ts">
/**
 * 移动端统一顶栏（2026-09-05 组长拍板：全局头像 + 页面标题 + 右侧功能扩展按钮）
 * 左 = 返回（可选，二级页）+ 全局头像（点击开账户抽屉，App.vue 全局挂载）；
 * 中 = 页面标题（X 式居中）；右侧 = actions 插槽（按页面功能放 1~2 个图标按钮）。
 */
import { computed } from 'vue'
import IconArrowLeft from '~icons/tabler/arrow-left'

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
      <button v-if="props.back" class="u-topbar__back" type="button" title="返回" aria-label="返回" @click="emit('back')">
        <IconArrowLeft />
      </button>
      <button class="u-topbar__ava" type="button" title="账户菜单" aria-label="账户菜单" @click="ui.openDrawer()">
        {{ avatarLetter }}
      </button>
    </div>
    <h1 class="u-topbar__title">{{ props.title }}</h1>
    <div class="u-topbar__acts">
      <slot name="actions" />
    </div>
  </header>
</template>
