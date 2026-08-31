<script setup lang="ts">
import { NButton, NInput, NTag } from 'naive-ui'
import { h } from 'vue'

import type { DataTableColumns } from 'naive-ui'

interface UserRow {
  id: number
  email: string
  level: string
  scenes: number
  score: number
  status: 'active' | 'disabled'
  joined: string
}

const users: UserRow[] = [
  { id: 1, email: 'lhr@example.com', level: 'L3', scenes: 42, score: 78.5, status: 'active', joined: '08-26' },
  { id: 2, email: 'xiaoxiao@example.com', level: 'L2', scenes: 17, score: 62.1, status: 'active', joined: '08-27' },
  { id: 3, email: 'faust@example.com', level: 'L4', scenes: 88, score: 91.3, status: 'disabled', joined: '08-28' },
]

const columns: DataTableColumns<UserRow> = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '邮箱', key: 'email' },
  {
    title: '水平',
    key: 'level',
    render: (row) => h(NTag, { size: 'small', bordered: false }, { default: () => row.level }),
  },
  { title: '完成场景', key: 'scenes', width: 90 },
  { title: '综合分', key: 'score', width: 90 },
  {
    title: '状态',
    key: 'status',
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.status === 'active' ? 'success' : 'error', bordered: false },
        { default: () => (row.status === 'active' ? '正常' : '禁用') },
      ),
  },
  { title: '注册', key: 'joined', width: 90 },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    render: () => [h(NButton, { size: 'small', quaternary: true }, { default: () => '详情' }), h(NButton, { size: 'small', quaternary: true, type: 'error' }, { default: () => '禁用' })],
  },
]
</script>

<template>
  <div>
    <header class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold">用户管理</h1>
        <p class="text-sm text-[#667085]">JWT 鉴权链路 M2 接入后可用；列表为演示数据</p>
      </div>
      <NButton round type="primary" disabled>+ 新增用户</NButton>
    </header>

    <section class="rounded-[12px] border border-[#E5E7EB] bg-white p-4">
      <div class="mb-3 flex items-center gap-3">
        <NInput size="small" placeholder="搜索邮箱 / 用户名" class="max-w-[280px]" />
        <NButton size="small" round secondary>查询</NButton>
      </div>
      <n-data-table
        :columns="columns"
        :data="users"
        :bordered="false"
        :pagination="{ pageSize: 10 }"
      />
    </section>
  </div>
</template>
