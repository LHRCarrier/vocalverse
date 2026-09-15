<script setup lang="ts">
/**
 * 管理员账号的新建 / 编辑弹窗（docs/50 §10.2 · `POST /admins` + `PATCH /admins/{id}`）。
 *
 * 两个刻意的设计：
 * 1. 编辑态必须选「变更原因」（§11.4：状态/权限变更要留原因）。弹窗本身就是二次确认，
 *    因此不再套一层 useDialog——两层弹窗只会让人点错。
 * 2. 口令规则按 §4.1 在**本地**先拦（10–64 位、不得与账号同名）：这条规则每次错都要
 *    打一次接口才知道，纯属浪费运营时间。
 */
import { computed, ref, watch } from 'vue'
import { NButton, NInput, NModal, NSelect, useMessage } from 'naive-ui'

import { consoleApi } from '@/api'
import type { AdminRoleRow, AdminUserRow } from '@/api'
import { useAuthStore } from '@/stores/auth'
import {
  ADMIN_UPDATE_REASONS,
  describeActionError,
  failureLines,
  type ActionFailure,
} from '@/views/content/actionReason'

const props = defineProps<{
  /** null = 新建 */
  target: AdminUserRow | null
  roles: AdminRoleRow[]
}>()

const show = defineModel<boolean>('show', { required: true })
const emit = defineEmits<{ saved: [] }>()

const message = useMessage()
/** `me` 的 id 用来挡住"改自己的角色"：服务端会以 46007 拒绝（`ConsoleRbacController.patchAdmin` 反提权①） */
const auth = useAuthStore()

const username = ref('')
const displayName = ref('')
const password = ref('')
const roleId = ref<number | null>(null)
const status = ref<'active' | 'disabled'>('active')
const reason = ref<string | null>(null)
const submitting = ref(false)
const failure = ref<ActionFailure | null>(null)

const isEdit = computed(() => props.target !== null)
const title = computed(() => (isEdit.value ? `编辑账号 · ${props.target?.username ?? ''}` : '新建管理员账号'))
const roleOptions = computed(() => props.roles.map((r) => ({ label: `${r.name}（${r.code}）`, value: r.id })))
const lines = computed(() => (failure.value ? failureLines(failure.value) : []))

/** 正在编辑自己：角色不可改（服务端硬拒），停用也不可（`patchAdmin` 会回 46007） */
const isSelf = computed(() => props.target !== null && props.target.id === auth.profile?.adminUserId)

function reset(): void {
  username.value = props.target?.username ?? ''
  displayName.value = props.target?.displayName ?? ''
  password.value = ''
  // 角色是**扁平** `roleId`（`ConsoleRbacController.AdminView`），v1 读的 `target.role.id` 后端不存在
  roleId.value = props.target?.roleId ?? (props.roles.length > 0 ? props.roles[0].id : null)
  status.value = props.target?.status === 'disabled' ? 'disabled' : 'active'
  reason.value = null
  failure.value = null
}

watch(show, (open) => {
  if (open) reset()
})

/** 返回第一条不满足的规则说明；全部通过返回 null */
function validate(): string | null {
  if (!isEdit.value && !username.value.trim()) return '请填写账号'
  if (!displayName.value.trim()) return '请填写显示名'
  if (!roleId.value) return '请选择角色'
  if (!isEdit.value) {
    const pwd = password.value
    if (pwd.length < 10 || pwd.length > 64) return '口令长度需为 10–64 位（docs/50 §4.1）'
    if (pwd === username.value.trim()) return '口令不得与账号相同（docs/50 §4.1）'
  }
  if (isEdit.value && !reason.value) return '请选择变更原因'
  return null
}

/**
 * PATCH 体（`ConsoleRbacController.AdminPatch`：displayName / roleId / status 三个**可空**字段）。
 *
 * 三个"不发"的取舍，都对着 Java 的判断写：
 * 1. 编辑自己时**不发 roleId**：`patchAdmin` 的反提权①直接回 46007（改自己一行即可自我提权）；
 * 2. 角色没变就不发（服务端只在 `!body.roleId().equals(e.getRoleId())` 时才动）；
 * 3. 状态没变就不发 —— 停用自己同样被 `patchAdmin` 以 46007 拒绝（会把控制台锁死）。
 */
function patchBody(
  target: AdminUserRow,
  nextRoleId: number,
): { displayName: string; roleId?: number; status?: 'active' | 'disabled' } {
  const body: { displayName: string; roleId?: number; status?: 'active' | 'disabled' } = {
    displayName: displayName.value.trim(),
  }
  if (!isSelf.value && nextRoleId !== target.roleId) body.roleId = nextRoleId
  if (status.value !== target.status) body.status = status.value
  return body
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
    if (props.target && roleId.value) {
      await consoleApi.updateAdmin(props.target.id, patchBody(props.target, roleId.value))
      message.success('账号已更新')
    } else if (roleId.value) {
      await consoleApi.createAdmin({
        username: username.value.trim(),
        displayName: displayName.value.trim(),
        password: password.value,
        roleId: roleId.value,
      })
      message.success('账号已创建')
    }
    show.value = false
    emit('saved')
  } catch (err) {
    // 46005（账号已存在）/ 46007（入参非法 / 改自己角色）等直接就地显示，不弹第二个弹窗
    failure.value = describeActionError(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <n-modal v-model:show="show" preset="card" :title="title" class="w-140" :mask-closable="false">
    <div class="mb-3">
      <div class="c-muted text-12px mb-1">账号（登录名）</div>
      <n-input v-model:value="username" :disabled="isEdit" placeholder="如 ops02" />
      <div v-if="isEdit" class="c-weak text-12px mt-1">账号是审计流水的外键，创建后不可修改。</div>
    </div>

    <div class="mb-3">
      <div class="c-muted text-12px mb-1">显示名</div>
      <n-input v-model:value="displayName" placeholder="如 运营小王" />
    </div>

    <div v-if="!isEdit" class="mb-3">
      <div class="c-muted text-12px mb-1">初始口令</div>
      <n-input v-model:value="password" type="password" show-password-on="click" placeholder="10–64 位，不得与账号相同" />
      <div class="c-weak text-12px mt-1">口令只在创建时设置，之后只能重置（服务端不存明文）。</div>
    </div>

    <div class="mb-3">
      <div class="c-muted text-12px mb-1">角色</div>
      <n-select v-model:value="roleId" :options="roleOptions" :disabled="isSelf" placeholder="请选择角色" />
      <div v-if="isSelf" class="c-weak text-12px mt-1">
        这是当前登录账号：服务端禁止修改自己的角色（反提权，`ConsoleRbacController.patchAdmin` 会回 46007），
        请由其他管理员操作。
      </div>
    </div>

    <div v-if="isEdit" class="mb-3">
      <div class="c-muted text-12px mb-1">账号状态</div>
      <n-select
        v-model:value="status"
        :disabled="isSelf"
        :options="[
          { label: '启用', value: 'active' },
          { label: '停用', value: 'disabled' },
        ]"
      />
      <div class="c-weak text-12px mt-1">
        停用会同时吊销该账号全部会话，下一个请求即失效（docs/50 §4.1）；不能停用自己（会把控制台锁死）。
      </div>
    </div>

    <div v-if="isEdit" class="mb-1">
      <div class="c-muted text-12px mb-1">变更原因（必填）</div>
      <n-select v-model:value="reason" :options="ADMIN_UPDATE_REASONS" placeholder="请选择变更原因" />
    </div>

    <div v-if="lines.length > 0" class="mt-3 text-12px" role="alert" style="color: var(--c-danger)">
      <p v-for="(line, index) in lines" :key="index" class="m-0 mb-1">{{ line }}</p>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="show = false">取消</n-button>
        <n-button type="primary" :loading="submitting" @click="onSubmit">
          {{ isEdit ? '保存' : '创建' }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>
