<script setup lang="ts">
/**
 * 重置管理员口令（docs/50 §10.2 · `POST /admins/{id}/password`）。
 *
 * 这是安全操作，故与上下架同等对待：**必须选原因**（§11.4 危险操作纪律），
 * 且不在界面上回显任何旧口令——服务端只存 BCrypt 哈希，前端也不该假装能"看一眼"。
 *
 * ⚠️ 两处与 v1 不同，都以 Java 为准：
 * 1. 请求体字段名是 **`password`**（`ConsoleRbacController.PasswordReset(@NotBlank String password)`），
 *    v1 发的 `newPassword` 会被 Jackson 忽略 → 服务端收到 null → 46007，重置永远失败；
 * 2. 重置**会吊销该账号全部会话并 bump token_epoch**（`rbac.invalidateAdmin`），
 *    所以旧文案"现有登录会话不受影响"是错的，页面必须说清"会被踢下线"。
 * 3. 原因只用于操作人确认，不随请求下发（该端点的 body 只有 `{password}`，详见 `actionReason.ts`）。
 */
import { computed, ref, watch } from 'vue'
import { NButton, NInput, NModal, NSelect, useMessage } from 'naive-ui'

import { consoleApi } from '@/api'
import type { AdminUserRow } from '@/api'
import { ADMIN_SECURITY_REASONS, describeActionError, failureLines, type ActionFailure } from '@/views/content/actionReason'

const props = defineProps<{ target: AdminUserRow | null }>()

const show = defineModel<boolean>('show', { required: true })
const emit = defineEmits<{ saved: [] }>()

const message = useMessage()

const password = ref('')
const confirmPassword = ref('')
const reason = ref<string | null>(null)
const submitting = ref(false)
const failure = ref<ActionFailure | null>(null)

const title = computed(() => `重置口令 · ${props.target?.username ?? ''}`)
const lines = computed(() => (failure.value ? failureLines(failure.value) : []))

watch(show, (open) => {
  if (!open) return
  password.value = ''
  confirmPassword.value = ''
  reason.value = null
  failure.value = null
})

function validate(): string | null {
  if (password.value.length < 10 || password.value.length > 64) return '口令长度需为 10–64 位（docs/50 §4.1）'
  if (password.value !== confirmPassword.value) return '两次输入的口令不一致'
  if (password.value === props.target?.username) return '口令不得与账号相同（docs/50 §4.1）'
  if (!reason.value) return '请选择重置原因'
  return null
}

async function onSubmit(): Promise<void> {
  const problem = validate()
  if (problem) {
    message.warning(problem)
    return
  }
  failure.value = null
  submitting.value = true
  try {
    if (props.target) await consoleApi.resetAdminPassword(props.target.id, { password: password.value })
    message.success('口令已重置；该账号的全部会话已被吊销，需用新口令重新登录')
    show.value = false
    emit('saved')
  } catch (err) {
    failure.value = describeActionError(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <n-modal v-model:show="show" preset="card" :title="title" class="w-130" :mask-closable="false">
    <p class="m-0 mb-3 c-muted text-13px">
      重置后旧口令立即失效；服务端同时会吊销该账号的全部会话并递增 token_epoch
      （`rbac.invalidateAdmin`），因此该管理员会被立刻踢下线，需要用新口令重新登录。
      请通过安全渠道把新口令单独告知本人。
    </p>

    <div class="mb-3">
      <div class="c-muted text-12px mb-1">新口令</div>
      <n-input v-model:value="password" type="password" show-password-on="click" placeholder="10–64 位" />
    </div>

    <div class="mb-3">
      <div class="c-muted text-12px mb-1">确认新口令</div>
      <n-input v-model:value="confirmPassword" type="password" show-password-on="click" placeholder="再输一次" />
    </div>

    <div class="mb-1">
      <div class="c-muted text-12px mb-1">重置原因（必填）</div>
      <n-select v-model:value="reason" :options="ADMIN_SECURITY_REASONS" placeholder="请选择重置原因" />
    </div>

    <div v-if="lines.length > 0" class="mt-3 text-12px" role="alert" style="color: var(--c-danger)">
      <p v-for="(line, index) in lines" :key="index" class="m-0 mb-1">{{ line }}</p>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="show = false">取消</n-button>
        <n-button type="primary" :loading="submitting" @click="onSubmit">重置口令</n-button>
      </div>
    </template>
  </n-modal>
</template>
