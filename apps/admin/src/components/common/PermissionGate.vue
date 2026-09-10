<script setup lang="ts">
/**
 * 权限门（docs/50 §4.3）。
 *
 * ⚠️ 这不是安全边界——**后端每个端点独立校验权限码**。
 * 这里只解决"点了才 403"的体验问题。
 */
import { computed } from 'vue'

import { useAuthStore } from '@/stores/auth'

const props = withDefaults(
  defineProps<{
    code: string | string[]
    /** true = 满足任一即可；默认需全部满足 */
    anyOf?: boolean
    /** 无权限时的替代内容（默认什么都不渲染） */
    fallback?: 'hide' | 'disable'
  }>(),
  { anyOf: false, fallback: 'hide' },
)

const auth = useAuthStore()

const allowed = computed(() =>
  props.anyOf ? auth.hasAny(props.code) : auth.hasPermission(props.code),
)
</script>

<template>
  <slot v-if="allowed" />
  <slot v-else-if="fallback === 'disable'" name="disabled">
    <span class="c-weak" style="font-size: 12px">无权限</span>
  </slot>
</template>
