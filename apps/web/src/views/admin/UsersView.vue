<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NInput, NTag } from 'naive-ui'

import type { DataTableColumns } from 'naive-ui'

import { fetchUsers, toggleUser } from '@/api/admin'
import type { AdminUser } from '@/api/m3-types'

const users = ref<AdminUser[]>([])
const query = ref('')
const loading = ref(true)
const error = ref<string | null>(null)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return users.value
  return users.value.filter(
    (u) => u.email.toLowerCase().includes(q) || u.nickname.toLowerCase().includes(q),
  )
})

const columns: DataTableColumns<AdminUser> = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '邮箱', key: 'email' },
  { title: '昵称', key: 'nickname' },
  {
    title: '水平',
    key: 'level',
    width: 70,
    render: (row) => h(NTag, { size: 'small', bordered: false }, { default: () => row.level }),
  },
  { title: '完成场景', key: 'scenes', width: 90 },
  { title: '综合分', key: 'score', width: 90 },
  { title: '注册', key: 'joined', width: 90 },
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
  {
    title: '操作',
    key: 'actions',
    width: 90,
    render: (row) =>
      h(
        NButton,
        {
          size: 'small',
          quaternary: true,
          type: row.status === 'active' ? 'error' : 'primary',
          onClick: () => onToggle(row),
        },
        { default: () => (row.status === 'active' ? '禁用' : '启用') },
      ),
  },
]

async function onToggle(row: AdminUser) {
  try {
    users.value = await toggleUser(row.id)
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(async () => {
  try {
    users.value = await fetchUsers()
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
      <h1 class="mb-2 text-xl font-bold">用户管理</h1>
      <p class="mb-4 text-sm text-[#667085]">用户列表 / 查询 / 禁用启用（docs/06 §9.3，mock）</p>
      <div class="flex items-center gap-3">
        <NInput v-model:value="query" size="small" placeholder="搜索邮箱 / 昵称" class="max-w-[280px]" />
      </div>
    </header>

    <p v-if="error" class="rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-xs text-[#B91C1C]">
      {{ error }}
    </p>

    <section class="rounded-[12px] border border-[#E5E7EB] bg-white p-4">
      <div v-if="loading" class="py-10 text-center text-sm text-[#667085]">加载中…</div>
      <n-data-table v-else :columns="columns" :data="filtered" :bordered="false" :pagination="{ pageSize: 10 }" />
    </section>
  </div>
</template>