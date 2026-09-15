<script setup lang="ts">
/**
 * 管理员账号（docs/50 §4.1 身份 + §10.2 端点）。
 *
 * 三条口径：
 * 1. 控制台账号与 App 用户**完全隔离**（§4.1：无外键、令牌不互通），所以本页只显示
 *    `admin_users`，不会去查用户表；
 * 2. 每个写动作单独用 `PermissionGate` 包住（§4.3）——没有 `console:admin:write` 的账号
 *    看不到「新建 / 编辑 / 重置口令」，只能看（read）与查会话；
 * 3. 「强制下线」放在会话抽屉里而不是行按钮：它吊销的是**该账号全部会话**（§10.2 端点语义），
 *    放在能看见会话列表的地方才不会被误解成"踢掉某一条"。
 */
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NDataTable, NInput, NPagination, NSelect } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

import { consoleApi } from '@/api'
import type { AdminRoleRow, AdminUserRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import PermissionGate from '@/components/common/PermissionGate.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { debounce, useAsync } from '@/composables/useAsync'
import { usePagedList } from '@/composables/usePagedList'
import { fmtDateTime, fmtInt, fmtRelative } from '@/utils/format'
import AdminFormModal from './AdminFormModal.vue'
import AdminPasswordModal from './AdminPasswordModal.vue'
import AdminSessionsDrawer from './AdminSessionsDrawer.vue'
import { accountLockNote, roleBadge } from './adminMeta'

type Filters = {
  q: string
  roleId: number | null
  status: string
}

const { items, total, page, pageCount, loading, error, errorCode, load, applyFilters, goPage } =
  usePagedList<AdminUserRow, Filters>(
    (q) =>
      consoleApi.listAdmins({
        page: q.page,
        page_size: q.page_size,
        q: q.q,
        status: q.status,
        roleId: q.roleId ?? undefined,
      }),
    { q: '', roleId: null, status: '' },
  )

const { state: rolesState, run: loadRoles } = useAsync<AdminRoleRow[]>(() => consoleApi.listRoles())

const keyword = ref('')
const roleId = ref<number | null>(null)
const status = ref<string | null>(null)

const showForm = ref(false)
const formTarget = ref<AdminUserRow | null>(null)
const showPassword = ref(false)
const passwordTarget = ref<AdminUserRow | null>(null)
const showSessions = ref(false)
const sessionsTarget = ref<AdminUserRow | null>(null)

// usePagedList 的 items 被标成 `{value:T[]}`，模板不会把它当 Ref 解包，故包一层 computed
const rows = computed(() => items.value)
// 同上：useAsync 的 state 也是 `{value:AsyncState}`，摊成模板能直接读的形态
const roleList = computed(() => rolesState.value.data ?? [])
const rolesError = computed(() => rolesState.value.error)
const roleOptions = computed(() =>
  roleList.value.map((r) => ({ label: `${r.name}（${r.code}）`, value: r.id })),
)

const search = debounce((value: string) => void applyFilters({ q: value.trim() }), 300)

function onKeyword(value: string): void {
  keyword.value = value
  search(value)
}

function onRole(value: number | null): void {
  roleId.value = value
  void applyFilters({ roleId: value })
}

function onStatus(value: string | null): void {
  status.value = value
  void applyFilters({ status: value ?? '' })
}

function openCreate(): void {
  formTarget.value = null
  showForm.value = true
}

function openEdit(row: AdminUserRow): void {
  formTarget.value = row
  showForm.value = true
}

function openPassword(row: AdminUserRow): void {
  passwordTarget.value = row
  showPassword.value = true
}

function openSessions(row: AdminUserRow): void {
  sessionsTarget.value = row
  showSessions.value = true
}

/** 会话被吊销后列表里的"最近登录"等信息也可能变，故整体重载 */
function reload(): void {
  void load()
  void loadRoles()
}

const columns = computed<DataTableColumns<AdminUserRow>>(() => [
  { title: '账号', key: 'username', width: 150, render: (row) => h('span', { class: 'c-mono' }, row.username) },
  { title: '显示名', key: 'displayName', minWidth: 140, ellipsis: { tooltip: true } },
  { title: '角色', key: 'role', width: 140, render: (row) => roleBadge(row) },
  {
    title: '状态',
    key: 'status',
    width: 160,
    render: (row) =>
      h('div', { class: 'flex flex-col gap-1' }, [
        h(StatusBadge, { kind: 'account', value: row.status }),
        // 登录失败锁定（§4.1：同账号 5 次 / 15 分钟）——不显示的话运营只能靠猜
        accountLockNote(row),
      ]),
  },
  {
    title: '最近登录',
    key: 'lastLoginAt',
    width: 200,
    render: (row) =>
      h('div', [
        h('div', fmtDateTime(row.lastLoginAt)),
        h('div', { class: 'c-weak text-12px' }, row.lastLoginIp ? `${fmtRelative(row.lastLoginAt)} · ${row.lastLoginIp}` : fmtRelative(row.lastLoginAt)),
      ]),
  },
  {
    title: '操作',
    key: 'actions',
    width: 230,
    render: (row) =>
      h('div', { class: 'flex gap-2' }, [
        // 写动作整组包在同一个权限门里：没有写权限时这一列只剩「会话」（只读）
        h(PermissionGate, { code: 'console:admin:write' }, {
          default: () => [
            h(NButton, { size: 'tiny', onClick: () => openEdit(row) }, { default: () => '编辑' }),
            h(NButton, { size: 'tiny', onClick: () => openPassword(row) }, { default: () => '重置口令' }),
          ],
        }),
        h(NButton, { size: 'tiny', onClick: () => openSessions(row) }, { default: () => '会话' }),
      ]),
  },
])

onMounted(() => reload())
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="管理员账号"
      desc="控制台账号独立于 App 用户：新建 / 编辑 / 重置口令 / 强制下线都在这里，全部写入审计。"
    >
      <template #actions>
        <PermissionGate code="console:admin:write">
          <n-button type="primary" @click="openCreate">新建账号</n-button>
        </PermissionGate>
      </template>
    </PageHeader>

    <div class="c-card">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <n-input :value="keyword" class="w-56" clearable placeholder="搜索账号 / 显示名" @update:value="onKeyword" />
        <n-select
          :value="roleId"
          class="w-48"
          :options="roleOptions"
          clearable
          placeholder="全部角色"
          @update:value="onRole"
        />
        <n-select
          :value="status"
          class="w-32"
          :options="[
            { label: '启用', value: 'active' },
            { label: '停用', value: 'disabled' },
          ]"
          clearable
          placeholder="全部状态"
          @update:value="onStatus"
        />
        <span class="c-weak text-12px">共 {{ fmtInt(total) }} 条</span>
        <span v-if="rolesError" class="text-12px" style="color: var(--c-warn)">
          角色列表加载失败（{{ rolesError }}），筛选与新建会缺少角色选项。
        </span>
      </div>

      <AsyncBlock
        :loading="loading"
        :error="error"
        :error-code="errorCode"
        :empty="rows.length === 0"
        empty-text="没有匹配的管理员账号"
        empty-hint="换个关键词，或清空角色 / 状态筛选"
      >
        <n-data-table
          :columns="columns"
          :data="rows"
          :row-key="(row: AdminUserRow) => row.id"
          :bordered="false"
          :single-line="false"
          :pagination="false"
          :scroll-x="1100"
          size="small"
        />
      </AsyncBlock>

      <div class="flex justify-end mt-4">
        <n-pagination :page="page" :page-count="pageCount" :page-slot="7" @update:page="goPage" />
      </div>
    </div>

    <AdminFormModal v-model:show="showForm" :target="formTarget" :roles="roleList" @saved="reload" />
    <AdminPasswordModal v-model:show="showPassword" :target="passwordTarget" @saved="reload" />
    <AdminSessionsDrawer v-model:show="showSessions" :target="sessionsTarget" @revoked="reload" />
  </div>
</template>
