<script setup lang="ts">
/**
 * 角色权限（docs/50 §4.2 权限模型 / §10.2 端点）——控制台 RBAC 的核心页。
 *
 * 布局刻意做成「左列表 + 右矩阵」而不是两个页面：授权永远发生在**某个角色**的上下文里，
 * 分成两页会让操作者反复在"我在改哪个角色"上出错。
 *
 * 分工：
 * - 本页负责角色 CRUD 与选中态、内置角色的保护性 UI；
 * - 矩阵（勾选 + 保存）在 `RoleMatrix.vue`，因为它是本页唯一会超过 350 行硬约束的部分。
 *
 * 注：`GET /roles` 与 `GET /permissions` 返回的是**数组**而非 `PageView`（§10.2），
 * 因此这两个数据源用 `useAsync` 而不是 `usePagedList`——权限目录是固定长度的目录数据，
 * 分页对它没有意义。
 */
import { computed, onMounted, ref } from 'vue'
import { NButton, useDialog, useMessage } from 'naive-ui'

import { consoleApi } from '@/api'
import type { AdminRoleRow, PermissionGroup } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import PermissionGate from '@/components/common/PermissionGate.vue'
import StatTile from '@/components/common/StatTile.vue'
import { useAsync } from '@/composables/useAsync'
import { fmtInt } from '@/utils/format'
import { ROLE_DELETE_REASONS, confirmWithReason } from '@/views/content/actionReason'
import RoleFormModal from './RoleFormModal.vue'
import RoleMatrix from './RoleMatrix.vue'

const dialog = useDialog()
const message = useMessage()

const { state: rolesState, run: loadRoles } = useAsync<AdminRoleRow[]>(() => consoleApi.listRoles())
const { state: permsState, run: loadPerms } = useAsync<PermissionGroup[]>(() => consoleApi.listPermissions())

const selectedId = ref<number | null>(null)
const showForm = ref(false)
const formTarget = ref<AdminRoleRow | null>(null)

const roles = computed(() => rolesState.value.data ?? [])
const groups = computed(() => permsState.value.data ?? [])
// useAsync 的 state 被标成 `{value:AsyncState}`（内部 cast），模板不认它是 Ref，故摊开四态
const rolesLoading = computed(() => rolesState.value.loading)
const rolesError = computed(() => rolesState.value.error)
const rolesErrorCode = computed(() => rolesState.value.errorCode)
const permsLoading = computed(() => permsState.value.loading)
const permsError = computed(() => permsState.value.error)
const permsErrorCode = computed(() => permsState.value.errorCode)
const selected = computed<AdminRoleRow | null>(() => roles.value.find((r) => r.id === selectedId.value) ?? null)
const permissionCount = computed(() => groups.value.reduce((sum, g) => sum + g.items.length, 0))
const builtinCount = computed(() => roles.value.filter((r) => r.builtin).length)

/** 刷新后保持选中：角色被删掉时右侧矩阵会指向一个已不存在的对象 */
async function reloadRoles(): Promise<void> {
  const list = await loadRoles()
  if (!list) return
  if (!list.some((r) => r.id === selectedId.value)) selectedId.value = list.length > 0 ? list[0].id : null
}

function openCreate(): void {
  formTarget.value = null
  showForm.value = true
}

function openEdit(): void {
  if (!selected.value) return
  formTarget.value = selected.value
  showForm.value = true
}

function onDelete(): void {
  const role = selected.value
  if (!role) return
  confirmWithReason(
    { dialog, message },
    {
      title: `确认删除角色「${role.name}」？`,
      detail: '删除会同时移除该角色的权限分配；账号本身保留，但会失去该角色带来的权限。',
      reasons: ROLE_DELETE_REASONS,
      positiveText: '删除角色',
      successText: '角色已删除',
      danger: true,
      note: role.builtin
        ? '内置角色不可删除（docs/50 §4.2）：服务端会直接返回 46006。'
        : `当前成员数 ${role.memberCount}：仍有成员时服务端返回 46006，请先把成员改到其他角色。`,
      submit: () => consoleApi.deleteRole(role.id),
      onSuccess: () => void reloadRoles(),
    },
  )
}

onMounted(() => {
  void reloadRoles()
  void loadPerms()
})
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="角色权限"
      desc="控制台角色与权限码分配：内置角色的 code 与存废受保护，权限可按岗位调整。"
    >
      <template #actions>
        <PermissionGate code="console:role:write">
          <n-button type="primary" @click="openCreate">新建角色</n-button>
        </PermissionGate>
      </template>
    </PageHeader>

    <div class="c-stat-row mb-4">
      <StatTile label="角色数" :value="fmtInt(roles.length)" :loading="rolesLoading" hint="含 4 个内置角色" />
      <StatTile
        label="内置角色"
        :value="fmtInt(builtinCount)"
        :loading="rolesLoading"
        hint="不可删除，code 不可改（docs/50 §4.2）"
      />
      <StatTile
        label="权限码总数"
        :value="fmtInt(permissionCount)"
        :loading="permsLoading"
        hint="来自 GET /permissions 目录"
      />
    </div>

    <div class="grid grid-cols-[320px_1fr] gap-4 items-start">
      <div class="c-card">
        <div class="c-card-head">
          <h2 class="c-card-title">角色</h2>
          <span class="c-weak text-12px">共 {{ fmtInt(roles.length) }} 个</span>
        </div>

        <AsyncBlock
          :loading="rolesLoading"
          :error="rolesError"
          :error-code="rolesErrorCode"
          :empty="roles.length === 0"
          empty-text="还没有任何角色"
          empty-hint="用右上角「新建角色」创建第一个"
          :min-height="200"
        >
          <ul class="list-none m-0 p-0">
            <li v-for="role in roles" :key="role.id">
              <button
                type="button"
                class="role-item"
                :class="{ 'role-item--active': role.id === selectedId }"
                @click="selectedId = role.id"
              >
                <span class="role-item-name">{{ role.name }}</span>
                <span class="c-mono c-weak">{{ role.code }}</span>
                <span v-if="role.builtin" class="c-badge c-badge--info">内置</span>
                <span class="c-weak text-12px ml-auto">{{ fmtInt(role.memberCount) }} 人</span>
              </button>
            </li>
          </ul>
        </AsyncBlock>
      </div>

      <div class="c-card">
        <AsyncBlock
          :loading="permsLoading"
          :error="permsError"
          :error-code="permsErrorCode"
          :empty="selected === null"
          empty-text="先在左侧选择一个角色"
          empty-hint="右侧矩阵按权限模块分组，可整模块勾选"
          :min-height="260"
        >
          <template v-if="selected">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="c-card-title">{{ selected.name }}</div>
                <div class="c-card-sub">{{ selected.description ?? '（无描述）' }}</div>
              </div>
              <PermissionGate code="console:role:write">
                <n-button size="small" @click="openEdit">编辑角色</n-button>
                <n-button
                  size="small"
                  type="error"
                  ghost
                  :disabled="selected.builtin"
                  :title="selected.builtin ? '内置角色不可删除（docs/50 §4.2）' : undefined"
                  @click="onDelete"
                >
                  删除角色
                </n-button>
              </PermissionGate>
            </div>

            <p
              v-if="selected.builtin"
              class="mt-2 mb-0 p-2 c-muted text-12px"
              style="background: var(--c-surface-sunken); border-radius: var(--c-ctl-radius)"
            >
              内置角色（builtin）：删除按钮禁用、code 不可修改，理由见 docs/50 §4.2——这些 code 是权限模型与审计的引用键；
              权限本身仍可调整。仍有成员的角色删除时会被服务端以 46006 拒绝。
            </p>

            <hr class="c-hairline">

            <RoleMatrix :role="selected" :groups="groups" @saved="reloadRoles" />
          </template>
        </AsyncBlock>
      </div>
    </div>

    <RoleFormModal v-model:show="showForm" :target="formTarget" @saved="reloadRoles" />
  </div>
</template>

<style scoped>
.role-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  margin-bottom: 4px;
  border: 1px solid transparent;
  border-radius: var(--c-ctl-radius);
  background: transparent;
  color: var(--c-text);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background var(--vv-t-micro) var(--vv-ease-out);
}
.role-item:hover {
  background: var(--c-surface-sunken);
}
.role-item--active {
  background: var(--c-primary-soft);
  border-color: var(--c-primary-soft);
  color: var(--c-primary);
}
.role-item-name {
  font-weight: 500;
}
</style>
