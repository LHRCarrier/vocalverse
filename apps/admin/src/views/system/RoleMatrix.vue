<script setup lang="ts">
/**
 * 角色 × 权限矩阵（docs/50 §4.2 权限目录 + §10.2 `PUT /roles/{id}/permissions`）。
 *
 * 三个非显然的处理：
 * 1. **目录外的权限码原样保留**。`super` 的权限码里可能带 `*` 通配（§4.2：由 RbacService 展开），
 *    界面上没有对应的勾选框；若保存时直接提交勾选集合，一次"保存"就会静默摘掉通配，
 *    把一个超管角色降级成普通角色。故保存 = 勾选集 ∪ 目录外码。
 * 2. **按 module 分组 + 模块级全选**：`GET /permissions` 本身就是按 module 分组的（§10.2），
 *    35 个码平铺一屏会让"这个角色到底能干什么"看不出来。
 * 3. 保存是状态变更，必须选原因（§11.4）；且提示"成员账号有 ≤15 分钟令牌滞后"（§4.1）。
 */
import { computed, ref, watch } from 'vue'
import { NButton, NCheckbox, NCheckboxGroup, useDialog, useMessage } from 'naive-ui'

import { consoleApi } from '@/api'
import type { AdminRoleRow, PermissionGroup } from '@/api'
import PermissionGate from '@/components/common/PermissionGate.vue'
import { ROLE_PERMISSION_REASONS, confirmWithReason } from '@/views/content/actionReason'

const props = defineProps<{
  role: AdminRoleRow
  groups: PermissionGroup[]
}>()

const emit = defineEmits<{ saved: [] }>()

const dialog = useDialog()
const message = useMessage()

const checked = ref<string[]>([])

const knownCodes = computed(() => new Set(props.groups.flatMap((g) => g.items.map((i) => i.code))))
const extraCodes = computed(() => props.role.permissionCodes.filter((c) => !knownCodes.value.has(c)))

/** 是否有未保存的改动（用于禁用"保存"并提示，避免误点） */
const dirty = computed(() => {
  const before = [...props.role.permissionCodes].sort().join('\n')
  const after = [...checked.value, ...extraCodes.value].sort().join('\n')
  return before !== after
})

const totalChecked = computed(() => checked.value.length + extraCodes.value.length)

function sync(): void {
  checked.value = props.role.permissionCodes.filter((c) => knownCodes.value.has(c))
}

// 角色切换、权限目录重载（首屏 catalog 后到时角色已选中）都要重算勾选
watch([() => props.role, () => props.groups], sync, { immediate: true })

function onChecked(value: Array<string | number> | null): void {
  checked.value = (value ?? []).map((v) => String(v))
}

const countFor = (group: PermissionGroup): number => group.items.filter((i) => checked.value.includes(i.code)).length

const isAllChecked = (group: PermissionGroup): boolean => group.items.every((i) => checked.value.includes(i.code))

function toggleModule(group: PermissionGroup, on: boolean): void {
  const codes = group.items.map((i) => i.code)
  const rest = checked.value.filter((c) => !codes.includes(c))
  checked.value = on ? [...rest, ...codes] : rest
}

function onSave(): void {
  confirmWithReason(
    { dialog, message },
    {
      title: `确认保存「${props.role.name}」的权限？`,
      detail: `将写入 ${totalChecked.value} 个权限码，影响该角色下的 ${props.role.memberCount} 个账号。`,
      reasons: ROLE_PERMISSION_REASONS,
      positiveText: '保存权限',
      successText: '权限已保存',
      note: props.role.builtin
        ? '这是内置角色：权限可以调整，但 code 不可修改、角色不可删除（docs/50 §4.2）。落在 token 里的权限最长 15 分钟才刷新（§4.1）。'
        : '权限码随令牌下发，该角色成员最长 15 分钟后才按新权限生效（docs/50 §4.1）。',
      submit: () => consoleApi.setRolePermissions(props.role.id, [...checked.value, ...extraCodes.value]),
      onSuccess: () => emit('saved'),
    },
  )
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3 mb-2">
      <div class="flex items-baseline gap-2">
        <span class="c-card-title">权限矩阵</span>
        <span class="c-weak text-12px">
          已选 {{ totalChecked }} 个权限码（目录内 {{ checked.length }} + 目录外 {{ extraCodes.length }}）
        </span>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="dirty" class="text-12px" style="color: var(--c-warn)">有未保存的改动</span>
        <PermissionGate code="console:role:write">
          <n-button size="small" :disabled="!dirty" @click="sync">撤销改动</n-button>
          <n-button size="small" type="primary" :disabled="!dirty" @click="onSave">保存权限</n-button>
        </PermissionGate>
      </div>
    </div>

    <div v-if="extraCodes.length > 0" class="mb-3 p-2 text-12px c-muted" style="background: var(--c-surface-sunken); border-radius: var(--c-ctl-radius)">
      该角色还带有权限目录之外的通配码（保存时原样保留，删不掉也不该被悄悄删掉）：
      <span v-for="code in extraCodes" :key="code" class="c-mono mr-2">{{ code }}</span>
    </div>

    <div v-for="group in groups" :key="group.module" class="mt-4">
      <div class="flex items-center justify-between gap-3 mb-2">
        <div class="flex items-baseline gap-2">
          <span class="text-13px font-600">{{ group.module }}</span>
          <span class="c-weak text-12px">{{ countFor(group) }} / {{ group.items.length }}</span>
        </div>
        <PermissionGate code="console:role:write">
          <n-button size="tiny" text @click="toggleModule(group, !isAllChecked(group))">
            {{ isAllChecked(group) ? '取消本模块' : '勾选本模块' }}
          </n-button>
        </PermissionGate>
      </div>
      <n-checkbox-group :value="checked" @update:value="onChecked">
        <div class="grid grid-cols-2 gap-x-4 gap-y-2">
          <n-checkbox
            v-for="item in group.items"
            :key="item.code"
            :value="item.code"
            :label="`${item.name}（${item.code}）`"
            :title="item.description ?? undefined"
          />
        </div>
      </n-checkbox-group>
    </div>
  </div>
</template>
