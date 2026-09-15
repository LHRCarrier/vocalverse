<script setup lang="ts">
/**
 * 移动端 · 统一头像（社区 S3 · docs/47 §5.2）
 *
 * 背景：仓内此前有 8 套头像实现（`.u-avatar` / `.u-comm-item__ava` / `.u-topbar__ava` /
 * `.u-comments__ava` / `.u-search__ava` / `.u-drawer__ava` / `.u-msg__ava` …，5 种尺寸、6 种圆角），
 * 社区 S3 要显示**真实头像**（user_profiles.avatar_url）→ 必须收敛成一处，否则每加一个页面就多一套。
 *
 * 契约：`size`（sm 28 / md 40 / lg 64）+ `shape`（circle 社交 / square 卡片），
 * 用 CSS 变量表达，**不改既有页面的视觉基线**（docs/31「不得改变已验收视觉基线」）：
 * 老调用点保持原尺寸/圆角由 size/shape 组合覆盖。
 *
 * 降级：无 avatarUrl 或加载失败 → 首字母 + tint 底色（与既有实现一致）。
 */
import { computed, ref, watch } from 'vue'

import { mediaUrl } from '@/api/media'

const props = withDefaults(
  defineProps<{
    /** 头像地址（后端 avatarUrl；相对路径会拼 PYTHON_BASE） */
    src?: string | null
    /** 昵称（取首字母做兜底） */
    name?: string | null
    /** tint 色（兜底底色；缺省用品牌深色） */
    tint?: string | null
    size?: 'sm' | 'md' | 'lg'
    shape?: 'circle' | 'square'
    /** 无障碍标签（缺省用昵称） */
    alt?: string
  }>(),
  { src: null, name: null, tint: null, alt: '', size: 'md', shape: 'circle' },
)

const failed = ref(false)
watch(
  () => props.src,
  () => {
    failed.value = false
  },
)

const showImg = computed(() => !!props.src && !failed.value)
const url = computed(() => mediaUrl(props.src))
const letter = computed(() => (props.name ?? '同').trim().slice(0, 1).toUpperCase())
</script>

<template>
  <span
    class="u-ava"
    :class="[`u-ava--${props.size}`, `u-ava--${props.shape}`]"
    :style="{ background: showImg ? undefined : (props.tint ?? 'var(--u-avatar-fallback)') }"
    :aria-label="props.alt || props.name || '头像'"
    role="img"
  >
    <img v-if="showImg" class="u-ava__img" :src="url" :alt="props.alt || props.name || ''" loading="lazy" decoding="async" @error="failed = true">
    <template v-else>{{ letter }}</template>
  </span>
</template>
