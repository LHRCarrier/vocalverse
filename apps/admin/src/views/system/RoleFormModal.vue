<script setup lang="ts">
/**
 * 角色新建 / 编辑弹窗（docs/50 §4.2 + §10.2 `POST /roles` · `PATCH /roles/{id}`）。
 *
 * 硬规则（§4.2）：内置角色 `code` 不可改。口径核实（2026-09-10）：
 * 后端 `ConsoleRbacController.RolePatch` **确实接收** `code`（`@Size(max = 32) String code`），
 * "编辑态不给改"是产品口径（code 是权限与审计的引用键），因此这里禁用输入框 ——
 * 不是因为"契约里没有这个字段"（v1 的注释把这一点写反了）。
 * 权限勾选不在这里做：新建出来的是空权限角色，权限在右侧矩阵里分配（一次一处，便于审计对账）。
 */
import { computed, ref, watch } from 'vue'
import { NButton, NInput, NModal, NSelect, useMessage } from 'naive-ui'

import { consoleApi } from '@/api'
import type { AdminRoleRow } from '@/api'
import { ROLE_EDIT_REASONS, describeActionError, failureLines, type ActionFailure } from '@/views/content/actionReason'

const props = defineProps<{ target: AdminRoleRow | null }>()

const show = defineModel<boolean>('show', { required: true })
const emit = defineEmits<{ saved: [] }>()

const message = useMessage()

const code = ref('')
const name = ref('')
const description = ref('')
const reason = ref<string | null>(null)
const submitting = ref(false)
const failure = ref<ActionFailure | null>(null)

const isEdit = computed(() => props.target !== null)
const title = computed(() => (isEdit.value ? `编辑角色 · ${props.target?.code ?? ''}` : '新建角色'))
const lines = computed(() => (failure.value ? failureLines(failure.value) : []))

watch(show, (open) => {
  if (!open) return
  code.value = props.target?.code ?? ''
  name.value = props.target?.name ?? ''
  description.value = props.target?.description ?? ''
  reason.value = null
  failure.value = null
})

/** 本页约定：与既有内置 code 风格一致（小写字母开头，可含数字与 _ - :） */
function validate(): string | null {
  if (!code.value.trim()) return '请填写角色 code'
  if (!/^[a-z][a-z0-9_:-]{1,31}$/.test(code.value.trim()))
    return 'code 需小写字母开头、总长 2–32、可含小写字母 / 数字 / _ - :（与内置角色风格一致）'
  if (!name.value.trim()) return '请填写角色名称'
  if (isEdit.value && !reason.value) return '请选择变更原因'
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
    if (props.target) {
      await consoleApi.updateRole(props.target.id, { name: name.value.trim(), description: description.value.trim() })
      message.success('角色已更新')    } else {
      // 权限码留空：新建后到右侧矩阵里分配（§4.2 权限分配是独立动作）
      await consoleApi.createRole({
        code: code.value.trim(),
        name: name.value.trim(),
        description: description.value.trim(),
        permissionCodes: [],
      })
      message.success('角色已创建，请在右侧矩阵分配权限')
    }
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
    <div class="mb-3">
      <div class="c-muted text-12px mb-1">角色 code</div>
      <n-input v-model:value="code" :disabled="isEdit" placeholder="如 ops_lead" />
      <div v-if="isEdit" class="c-weak text-12px mt-1">
        code 是权限与审计的引用键：内置角色的 code 不可修改（docs/50 §4.2），本页也不提供修改入口。
      </div>
      <div v-else class="c-weak text-12px mt-1">创建后不可修改，请按岗位命名。</div>
    </div>

    <div class="mb-3">
      <div class="c-muted text-12px mb-1">角色名称</div>
      <n-input v-model:value="name" placeholder="如 运营主管" />
    </div>

    <div class="mb-3">
      <div class="c-muted text-12px mb-1">描述</div>
      <n-input v-model:value="description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="这个角色负责什么（会显示在角色列表里）" />
    </div>

    <div v-if="isEdit" class="mb-1">
      <div class="c-muted text-12px mb-1">变更原因（必填）</div>
      <n-select v-model:value="reason" :options="ROLE_EDIT_REASONS" placeholder="请选择变更原因" />
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
