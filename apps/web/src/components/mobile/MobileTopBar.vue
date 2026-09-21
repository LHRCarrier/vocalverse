<script setup lang="ts">
/**
 * 移动端统一顶栏（2026-09-05 组长拍板：全局头像 + 页面标题 + 右侧功能扩展按钮；
 * 2026-09-09 组长反馈调整：离开钮从左侧移到右侧 actions 末尾——X 范式「左侧=身份入口，
 * 右侧=操作」，头像左一更干净；明确回口保留（系统返回手势在 WebView 壳/历史栈中不可靠））
 * 左 = 全局头像（点击开账户抽屉，App.vue 全局挂载）；
 * 中 = 页面标题（X 式居中）；右侧 = actions 插槽（按页面功能放按钮）+ 离开钮（可选）。
 *
 * 2026-09-21（组长反馈：改语言/切领域要滑回顶部）：顶栏吸顶常驻 + 社交 App 惯例的方向感知
 * （下滚收起、上滚出现）——滚动逻辑在 useAutoHideOnScroll；宿主 = 包在 `.u-head` 吸顶区里时
 * 收起整块（顶栏 + 页首控制行），否则收起顶栏自身（见 mobile-uic.css「页首吸顶区」段）。
 */
import { ref } from 'vue'
import IconLogout from '~icons/tabler/logout'

import MobileAvatar from '@/components/mobile/MobileAvatar.vue'
import { useAutoHideOnScroll } from '@/composables/useAutoHideOnScroll'
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

const barEl = ref<HTMLElement | null>(null)
useAutoHideOnScroll(() => barEl.value?.closest<HTMLElement>('.u-head') ?? barEl.value)
</script>

<template>
  <header ref="barEl" class="u-topbar">
    <div class="u-topbar__left">
      <!-- 头像固定最左侧（组长定规：左侧不可有其他图标）。
           2026-09-09：换 MobileAvatar —— 此前这里写死首字母，用户设了真实头像后
           只有侧边抽屉显示新头像、顶栏仍是字母（组长手机实测 bug）。 -->
      <button class="u-topbar__ava" type="button" title="账户菜单" aria-label="账户菜单" @click="ui.openDrawer()">
        <MobileAvatar
          :src="auth.me?.avatarUrl"
          :name="auth.me?.nickname ?? auth.me?.username"
          :tint="auth.me?.tint"
          size="sm"
        />
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
