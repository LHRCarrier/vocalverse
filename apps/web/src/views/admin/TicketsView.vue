<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { NButton, NTag } from 'naive-ui'

import type { DataTableColumns } from 'naive-ui'

import { fetchTickets, updateTicket } from '@/api/admin'
import type { AdminTicket, TicketStatus } from '@/api/m3-types'

const tickets = ref<AdminTicket[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const STATUS_FLOW: TicketStatus[] = ['new', 'processing', 'resolved', 'closed']
const STATUS_LABEL: Record<TicketStatus, string> = {
  new: '新建',
  processing: '处理中',
  resolved: '已解决',
  closed: '关闭',
}
const STATUS_COLOR: Record<TicketStatus, { color: string; textColor: string }> = {
  new: { color: '#FEF3C7', textColor: '#B45309' },
  processing: { color: '#F0F9FF', textColor: '#0369A1' },
  resolved: { color: '#ECFDF5', textColor: '#15803D' },
  closed: { color: '#F3F4F6', textColor: '#667085' },
}

function advance(s: TicketStatus): TicketStatus {
  const i = STATUS_FLOW.indexOf(s)
  return STATUS_FLOW[Math.min(i + 1, STATUS_FLOW.length - 1)]
}

const columns: DataTableColumns<AdminTicket> = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '主题', key: 'subject' },
  { title: '用户', key: 'user', width: 110 },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render: (row) =>
      h(
        NTag,
        { size: 'small', round: true, bordered: false, color: STATUS_COLOR[row.status] },
        { default: () => STATUS_LABEL[row.status] },
      ),
  },
  { title: '创建时间', key: 'createdAt', width: 130 },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    render: (row) =>
      row.status === 'closed'
        ? ''
        : h(
            NButton,
            { size: 'small', quaternary: true, type: 'primary', onClick: () => onAdvance(row) },
            { default: () => `→ ${STATUS_LABEL[advance(row.status)]}` },
          ),
  },
]

async function onAdvance(row: AdminTicket) {
  try {
    tickets.value = await updateTicket(row.id, advance(row.status))
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(async () => {
  try {
    tickets.value = await fetchTickets()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-4">
    <header>
      <h1 class="mb-2 text-xl font-bold">工单</h1>
      <p class="text-sm text-[#667085]">状态流转：新建 / 处理中 / 已解决 / 关闭（docs/06 §9.3，mock）</p>
    </header>

    <p v-if="error" class="rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-xs text-[#B91C1C]">
      {{ error }}
    </p>

    <section class="rounded-[12px] border border-[#E5E7EB] bg-white p-4">
      <div v-if="loading" class="py-10 text-center text-sm text-[#667085]">加载中…</div>
      <n-data-table v-else :columns="columns" :data="tickets" :bordered="false" :pagination="{ pageSize: 10 }" />
    </section>
  </div>
</template>