<script setup lang="ts">
/**
 * 运营 · 工单（docs/50 §6.1 / §10.2；docs/06 §9.6）。
 *
 * ⚠️ **本页为什么必须存在**：旧管理端的 `AdminTicketController` 已随"旧管理端整体退役"删除
 * （docs/50 §15.5），因此**工单功能在这里是唯一入口**——没有本页，用户在 App 里提交的
 * 反馈/报错/内容纠误就**没有任何人能处理**（功能回退）。这正是退役复核项 ① 要防的事。
 *
 * 状态机与处置弹窗在 `ticketFlow.ts`（前端只用于可达性，权威在服务端 `TicketWorkflowService`）。
 */
import { computed, h, onMounted } from 'vue'
import { NButton, NDataTable, NPagination, NSelect, useDialog, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

import { consoleApi } from '@/api'
import type { TicketRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import PermissionGate from '@/components/common/PermissionGate.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { usePagedList } from '@/composables/usePagedList'
import { fmtDateTime, fmtInt, fmtRelative } from '@/utils/format'

import { TICKET_KIND_OPTIONS, TICKET_STATUS_OPTIONS, openTicketHandle } from './ticketFlow'

const dialog = useDialog()
const message = useMessage()

interface Filters extends Record<string, unknown> {
  status: string
  kind: string
}

const list = usePagedList<TicketRow, Filters>(
  (q) => consoleApi.listTickets(q),
  { status: '', kind: '' },
  20,
)

onMounted(() => void list.load())

/** 包装成 computed：模板才能把 `usePagedList` 的 ref 直接当数组用（同其它内容页） */
const rows = computed(() => list.items.value)

function handle(row: TicketRow): void {
  openTicketHandle({ dialog, message, onDone: () => list.load() }, row)
}

const columns = computed<DataTableColumns<TicketRow>>(() => [
  { title: 'ID', key: 'id', width: 70, render: (row) => h('span', { class: 'c-num' }, String(row.id)) },
  {
    title: '类型',
    key: 'kind',
    width: 96,
    render: (row) => h(StatusBadge, { kind: 'ticketKind', value: String(row.kind) }),
  },
  {
    title: '标题 / 内容',
    key: 'title',
    minWidth: 260,
    render: (row) =>
      h('div', {}, [
        h('div', { style: 'font-weight:500' }, row.title ?? '（无标题）'),
        // 纯文本插值：用户内容绝不 v-html（docs/13:83 存储型 XSS 红线）
        h('div', { class: 'c-weak', style: 'font-size:11.5px' }, row.content.slice(0, 90)),
      ]),
  },
  {
    title: '关联对象',
    key: 'target',
    width: 118,
    render: (row) =>
      row.targetType
        ? h('span', { class: 'c-mono' }, `${row.targetType}#${row.targetId ?? '—'}`)
        : h('span', { class: 'c-weak' }, '—'),
  },
  {
    title: '提交用户',
    key: 'userId',
    width: 92,
    render: (row) => h('span', { class: 'c-num' }, `#${row.userId}`),
  },
  {
    title: '状态',
    key: 'status',
    width: 92,
    render: (row) => h(StatusBadge, { kind: 'ticket', value: String(row.status) }),
  },
  {
    title: '处理人',
    key: 'adminId',
    width: 84,
    render: (row) =>
      row.adminId === null
        ? h('span', { class: 'c-weak' }, '未认领')
        : h('span', { class: 'c-num' }, `#${row.adminId}`),
  },
  {
    title: '提交时间',
    key: 'createdAt',
    width: 128,
    render: (row) => h('span', { title: fmtDateTime(row.createdAt) }, fmtRelative(row.createdAt)),
  },
  {
    title: '操作',
    key: 'actions',
    width: 96,
    render: (row) =>
      h(
        PermissionGate,
        { code: 'content:ticket:write' },
        {
          default: () =>
            h(
              NButton,
              { size: 'small', quaternary: true, type: 'primary', onClick: () => handle(row) },
              { default: () => '处置' },
            ),
          disabled: () => h('span', { class: 'c-weak', style: 'font-size:12px' }, '无权限'),
        },
      ),
  },
])
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="工单"
      desc="用户提交的反馈 / 报错 / 内容纠误。状态机 新建 → 处理中 → 已解决 → 已关闭，禁回退、已关闭为终态（服务端强制）。"
    />

    <section class="c-card">
      <div class="c-card-head">
        <div>
          <h2 class="c-card-title">工单列表</h2>
          <p class="c-card-sub">
            这是工单的**唯一**处理入口（旧管理端工单面已随旧管理端退役，docs/50 §15.5）
          </p>
        </div>
        <div class="tk-filters">
          <n-select
            v-model:value="list.filters.value.status"
            class="w-[140px]"
            size="small"
            :options="TICKET_STATUS_OPTIONS"
            @update:value="list.applyFilters({})"
          />
          <n-select
            v-model:value="list.filters.value.kind"
            class="w-[140px]"
            size="small"
            :options="TICKET_KIND_OPTIONS"
            @update:value="list.applyFilters({})"
          />
        </div>
      </div>

      <AsyncBlock
        :loading="list.loading.value"
        :error="list.error.value"
        :error-code="list.errorCode.value"
        :empty="!rows.length"
        empty-text="没有符合条件的工单"
        empty-hint="用户提交的反馈/报错/内容纠误会出现在这里"
        :min-height="220"
      >
        <n-data-table
          :columns="columns"
          :data="rows"
          :row-key="(row: TicketRow) => row.id"
          size="small"
          :bordered="false"
        />
        <div class="tk-pager">
          <span class="c-weak">共 {{ fmtInt(list.total.value) }} 条</span>
          <n-pagination
            :page="list.page.value"
            :page-count="list.pageCount.value"
            size="small"
            @update:page="list.goPage"
          />
        </div>
      </AsyncBlock>
    </section>
  </div>
</template>

<style scoped>
.tk-filters {
  display: flex;
  gap: 6px;
}
.tk-pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  font-size: 12.5px;
}
</style>
