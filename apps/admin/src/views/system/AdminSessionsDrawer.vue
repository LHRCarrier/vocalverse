<script setup lang="ts">
/**
 * 在线会话抽屉（docs/50 §10.2 · `GET /admins/sessions` + `DELETE /admins/{id}/sessions`）。
 *
 * 为什么把会话放在抽屉而不是单独页面：会话是"账号行的下钻信息"，
 * 离开账号上下文单独看没有意义；抽屉也避免在列表与详情之间来回跳。
 * 「强制下线」是吊销**该账号全部会话**（端点语义），不是单条会话——
 * 文案必须写清楚，否则管理员会以为只踢掉一行。
 *
 * ⚠️ 三处按 Java 源修正（2026-09-10）：
 * 1. 端点是**全局** `GET /admins/sessions`，参数只有 `page`/`page_size`，**没有** `adminUserId`
 *    —— v1 打的是 `GET /admins/{id}/sessions`（不存在，404）。现在拉全局在线会话后按
 *    `adminUserId` 过滤，见 `consoleApi.listAdminSessions`；
 * 2. `SessionView` 有 `adminUsername`，**没有** `current` 字段 —— 「当前会话」这一列是前端臆造的，
 *    已删掉；改用它真实提供的 `adminUsername` 列；
 * 3. 全局列表可能整页都是别人的会话，因此扫描有页数上限；够不到末尾时页面**明说**可能不全，
 *    而不是假装列全了。
 */
import { computed, h, watch } from 'vue'
import { NButton, NDataTable, NDrawer, NDrawerContent, useDialog, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

import { consoleApi } from '@/api'
import type { AdminSessionRow, AdminUserRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PermissionGate from '@/components/common/PermissionGate.vue'
import { useAsync } from '@/composables/useAsync'
import { useAuthStore } from '@/stores/auth'
import { fmtDateTime, fmtRelative } from '@/utils/format'
import { ADMIN_SECURITY_REASONS, confirmWithReason } from '@/views/content/actionReason'

const props = defineProps<{ target: AdminUserRow | null }>()

const show = defineModel<boolean>('show', { required: true })
const emit = defineEmits<{ revoked: [] }>()

const dialog = useDialog()
const message = useMessage()
/** 当前登录会话 id（`MeView.sessionId`）：用它标出"就是我这一条"，而不是冒充后端字段 */
const auth = useAuthStore()

const { state, run } = useAsync(() =>
  props.target
    ? consoleApi.listAdminSessions(props.target.id)
    : Promise.resolve({ items: [] as AdminSessionRow[], complete: true }),
)

// useAsync 把 state 标成 `{value:AsyncState}`（内部 cast），模板不认它是 Ref，
// 故把四态各自摊成 computed，模板拿到的就是布尔 / 数组本身
const sessions = computed(() => state.value.data?.items ?? [])
const scanComplete = computed(() => state.value.data?.complete ?? true)
const loading = computed(() => state.value.loading)
const loadError = computed(() => state.value.error)
const loadErrorCode = computed(() => state.value.errorCode)

// 打开时加载；目标账号切换时重载（否则会看到上一个账号的会话）
watch([show, () => props.target?.id], ([open]) => {
  if (open) void run()
})

const columns = computed<DataTableColumns<AdminSessionRow>>(() => [
  { title: '会话 id', key: 'id', width: 90, render: (row) => h('span', { class: 'c-mono' }, String(row.id)) },
  {
    title: '账号',
    key: 'adminUsername',
    width: 130,
    render: (row) =>
      h('span', { class: 'c-mono' }, [
        row.adminUsername || '—',
        // 只有 id 与当前登录会话相同时才标注；后端不返回"哪个是当前会话"，这是前端自己算的
        row.id === auth.sessionId ? h('span', { class: 'c-badge c-badge--info ml-2' }, '当前') : null,
      ]),
  },
  { title: '签发时间', key: 'issuedAt', width: 180, render: (row) => fmtDateTime(row.issuedAt) },
  {
    title: '过期时间',
    key: 'expiresAt',
    width: 180,
    render: (row) =>
      h('div', [
        h('div', fmtDateTime(row.expiresAt)),
        h('div', { class: 'c-weak text-12px' }, fmtRelative(row.expiresAt)),
      ]),
  },
  { title: '来源 IP', key: 'ip', width: 130, render: (row) => h('span', { class: 'c-mono' }, row.ip ?? '—') },
  { title: 'User-Agent', key: 'userAgent', ellipsis: { tooltip: true }, render: (row) => row.userAgent ?? '—' },
])

function onRevoke(): void {
  const target = props.target
  if (!target) return
  confirmWithReason(
    { dialog, message },
    {
      title: `确认强制下线「${target.displayName}」？`,
      detail: '会吊销该账号的全部控制台会话（refresh token 一次性轮换，旧令牌随即失效）。',
      reasons: ADMIN_SECURITY_REASONS,
      positiveText: '强制下线',
      successText: '已吊销该账号全部会话',
      danger: true,
      note: '该操作作用于全部会话，不是只踢掉其中一条；若目标是本人，操作后本页会因令牌失效跳回登录页。',
      submit: () => consoleApi.revokeAdminSessions(target.id),
      onSuccess: () => {
        void run()
        emit('revoked')
      },
    },
  )
}
</script>

<template>
  <n-drawer v-model:show="show" :width="720" placement="right">
    <n-drawer-content :title="`在线会话 · ${target?.displayName ?? ''}`" closable>
      <div class="flex items-center justify-between gap-3 mb-3">
        <span class="c-muted text-12px">
          会话即 `admin_sessions` 行：access token 15 分钟内自然过期，refresh token 吊销后立即失效（docs/50 §4.1）。
        </span>
        <PermissionGate code="console:admin:write">
          <n-button type="primary" ghost :disabled="sessions.length === 0" @click="onRevoke">强制下线</n-button>
        </PermissionGate>
      </div>

      <p v-if="!scanComplete && sessions.length > 0" class="m-0 mb-3 text-12px" style="color: var(--c-warn)">
        会话接口是全局在线会话列表（没有按账号过滤的参数），本页按账号筛选时已达到扫描页数上限，
        因此下表可能不是该账号的全部会话。
      </p>

      <AsyncBlock
        :loading="loading"
        :error="loadError"
        :error-code="loadErrorCode"
        :empty="sessions.length === 0"
        empty-text="该账号当前没有在线会话"
        empty-hint="账号已停用或令牌已被吊销时会看不到会话；也可能是全局会话已超出本页扫描上限"
        :min-height="120"
      >
        <n-data-table
          :columns="columns"
          :data="sessions"
          :row-key="(row: AdminSessionRow) => row.id"
          :bordered="false"
          :single-line="false"
          :pagination="false"
          :scroll-x="800"
          size="small"
        />
      </AsyncBlock>
    </n-drawer-content>
  </n-drawer>
</template>
