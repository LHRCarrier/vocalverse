<script setup lang="ts">
/**
 * 异步区域四态壳（docs/50 §11.4 硬规则：所有异步区域必须包裹）。
 *
 * 存在的理由：控制台最常见的缺陷是"接口失败 → 白屏 → 没人知道为什么"。
 * 这里强制把 loading / error / empty / ready 四态都画出来，并把错误码与
 * `X-Request-Id` 一并展示（便于对着服务端日志排查）。
 */
import IconAlertCircle from '~icons/tabler/alert-circle'
import IconInbox from '~icons/tabler/inbox'
import IconLoader2 from '~icons/tabler/loader-2'

import { getLastRequestId } from '@/api'

withDefaults(
  defineProps<{
    loading?: boolean
    error?: string | null
    errorCode?: number | null
    /** 数据为空（且不在 loading / error 态）时展示空态 */
    empty?: boolean
    emptyText?: string
    /** 空态下的下一步引导（可选） */
    emptyHint?: string
    minHeight?: number
  }>(),
  {
    loading: false,
    error: null,
    errorCode: null,
    empty: false,
    emptyText: '暂无数据',
    emptyHint: undefined,
    minHeight: 160,
  },
)

const requestId = getLastRequestId()
</script>

<template>
  <div class="c-async" :style="{ minHeight: `${minHeight}px` }">
    <div v-if="loading" class="c-async-state" role="status" aria-live="polite">
      <IconLoader2 class="c-spin" width="20" height="20" aria-hidden="true" />
      <span>加载中…</span>
    </div>

    <div v-else-if="error" class="c-async-state c-async-state--error" role="alert">
      <IconAlertCircle width="20" height="20" aria-hidden="true" />
      <span>{{ error }}</span>
      <span v-if="errorCode" class="c-mono c-weak">code={{ errorCode }}</span>
      <span v-if="requestId" class="c-mono c-weak">request-id={{ requestId }}</span>
      <slot name="error-actions" />
    </div>

    <div v-else-if="empty" class="c-async-state">
      <IconInbox width="20" height="20" aria-hidden="true" />
      <span>{{ emptyText }}</span>
      <span v-if="emptyHint" class="c-weak">{{ emptyHint }}</span>
    </div>

    <slot v-else />
  </div>
</template>

<style scoped>
.c-async {
  display: flex;
  flex-direction: column;
}
.c-async-state {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--c-text-2);
  font-size: 13px;
}
.c-async-state--error {
  color: var(--c-danger);
}
.c-spin {
  animation: c-spin 0.9s linear infinite;
}
@keyframes c-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .c-spin {
    animation: none;
  }
}
</style>
