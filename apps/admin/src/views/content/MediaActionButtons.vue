<script setup lang="ts">
/**
 * 媒体资产的「隐藏 / 恢复」按钮（docs/50 §6.1 第 5 条 + §10.3 Python 端点）。
 *
 * 媒体与审核的联动：隐藏后 `media_assets.status='hidden'`，被隐藏的资产不再允许被引用
 * （§6.1：媒体需 `status='ready'` 才可被引用）。因此这是状态变更操作，
 * 走统一确认框 + 必选原因（§11.4）；`deleted` 是终态，页面上不提供反向操作。
 */
import { computed } from 'vue'
import { NButton, useDialog, useMessage } from 'naive-ui'

import { opsApi } from '@/api'
import type { MediaStatus } from '@/api'
import PermissionGate from '@/components/common/PermissionGate.vue'
import { MEDIA_HIDE_REASONS, MEDIA_RESTORE_REASONS, confirmWithReason } from './actionReason'

const props = defineProps<{
  publicId: string
  /** 取值集与 models/media.py:65 的 CHECK 一致：ready|hidden|deleted */
  status: MediaStatus
}>()

const emit = defineEmits<{ done: [] }>()

const dialog = useDialog()
const message = useMessage()

const isHidden = computed(() => props.status === 'hidden')

function onClick(): void {
  confirmWithReason(
    { dialog, message },
    {
      title: isHidden.value ? '确认恢复该媒体资产？' : '确认隐藏该媒体资产？',
      detail: isHidden.value
        ? '恢复后 status 回到 ready，可再次被内容引用。'
        : '隐藏后 status=hidden，该资产不再允许被引用（docs/50 §6.1）；文件本身不删除。',
      reasons: isHidden.value ? MEDIA_RESTORE_REASONS : MEDIA_HIDE_REASONS,
      positiveText: isHidden.value ? '恢复' : '隐藏',
      successText: isHidden.value ? '已恢复' : '已隐藏',
      danger: !isHidden.value,
      note: `public_id：${props.publicId}`,
      submit: () => opsApi.hideMedia(props.publicId, !isHidden.value),
      onSuccess: () => emit('done'),
    },
  )
}
</script>

<template>
  <PermissionGate code="content:media:write">
    <n-button v-if="status !== 'deleted'" size="small" :type="isHidden ? 'primary' : 'default'" @click="onClick">
      {{ isHidden ? '恢复' : '隐藏' }}
    </n-button>
    <span v-else class="c-weak text-12px">已删除（终态）</span>
  </PermissionGate>
</template>
