<script setup lang="ts">
/**
 * 题目归档按钮（`DELETE /content/questions/{id}` → `status='archived'`）。
 *
 * 为什么不复用 `PublishActionButton`：那个组件走的是 `POST /content/{domain}/{id}/publish`
 * 三态上下架（`{status}` 请求体 + `content:{domain}:publish` 权限码），而题库**两样都没有**——
 * 没有 `content:question:publish` 这个权限码，题目也只有 `published|archived` 两态。
 * 硬套的结果是一个永远返回 46002 的按钮（越权）或一次打错端点的 404。
 *
 * 归档是状态变更，按 §11.4 走统一确认框 + 必选原因；`archived` 之后不再在用户端出现，
 * 但**记录不删**（题目被历史作答引用，物理删除会破坏记录完整性）。
 */
import { NButton, useDialog, useMessage } from 'naive-ui'

import { consoleApi } from '@/api'
import type { QuestionRow } from '@/api'
import PermissionGate from '@/components/common/PermissionGate.vue'
import { QUESTION_ARCHIVE_REASONS, confirmWithReason } from './actionReason'

const props = defineProps<{ row: QuestionRow }>()
const emit = defineEmits<{ done: [] }>()

const dialog = useDialog()
const message = useMessage()

function onClick(): void {
  const label = `第 ${props.row.examRevision ?? '?'} 卷 / ${props.row.itemIndex ?? '?'} 题`
  confirmWithReason(
    { dialog, message },
    {
      title: '确认归档该题目？',
      detail: '归档后该题不再出现在用户端试卷中（历史作答记录保留）。',
      reasons: QUESTION_ARCHIVE_REASONS,
      positiveText: '归档',
      successText: '已归档',
      danger: true,
      note: `${label}：${props.row.prompt ?? ''}`,
      submit: () => consoleApi.archiveQuestion(props.row.id),
      onSuccess: () => emit('done'),
    },
  )
}
</script>

<template>
  <PermissionGate code="content:question:write">
    <n-button v-if="row.status !== 'archived'" size="small" quaternary @click="onClick">归档</n-button>
    <span v-else class="c-weak text-12px">已归档</span>
  </PermissionGate>
</template>
