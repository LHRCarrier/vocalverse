<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import {
  NButton,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NTag,
} from 'naive-ui'

import type { DataTableColumns } from 'naive-ui'

import { createScene, fetchScenes, toggleScene, updateScene } from '@/api/admin'
import type { AdminScene } from '@/api/m3-types'

const scenes = ref<AdminScene[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const showModal = ref(false)
const editingId = ref<number | null>(null)
const form = ref({ title: '', sceneType: 'cafe', difficulty: 2 })

const sceneTypes = [
  { label: '咖啡馆', value: 'cafe' },
  { label: '机场', value: 'airport' },
  { label: '面试', value: 'interview' },
  { label: '图书馆', value: 'library' },
]

const columns: DataTableColumns<AdminScene> = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '标题', key: 'title' },
  {
    title: '类型',
    key: 'sceneType',
    render: (row) => sceneTypes.find((s) => s.value === row.sceneType)?.label ?? row.sceneType,
  },
  { title: '难度', key: 'difficulty', width: 80 },
  {
    title: '状态',
    key: 'status',
    width: 90,
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.status === 'on' ? 'success' : 'default', bordered: false },
        { default: () => (row.status === 'on' ? '上架' : '下架') },
      ),
  },
  {
    title: '操作',
    key: 'actions',
    width: 160,
    render: (row) => [
      h(NButton, { size: 'small', quaternary: true, onClick: () => openEdit(row) }, { default: () => '编辑' }),
      h(
        NButton,
        { size: 'small', quaternary: true, type: row.status === 'on' ? 'warning' : 'primary', onClick: () => onToggle(row) },
        { default: () => (row.status === 'on' ? '下架' : '上架') },
      ),
    ],
  },
]

function openCreate() {
  editingId.value = null
  form.value = { title: '', sceneType: 'cafe', difficulty: 2 }
  showModal.value = true
}

function openEdit(row: AdminScene) {
  editingId.value = row.id
  form.value = { title: row.title, sceneType: row.sceneType, difficulty: row.difficulty }
  showModal.value = true
}

async function save() {
  try {
    if (editingId.value == null) {
      scenes.value = await createScene({ ...form.value, status: 'off' })
    } else {
      scenes.value = await updateScene(editingId.value, { ...form.value })
    }
    showModal.value = false
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function onToggle(row: AdminScene) {
  try {
    scenes.value = await toggleScene(row.id)
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(async () => {
  try {
    scenes.value = await fetchScenes()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-4">
    <header class="flex items-start justify-between">
      <div>
        <h1 class="mb-2 text-xl font-bold">场景库</h1>
        <p class="text-sm text-[#667085]">场景表格 + 上下架 + 增删改（docs/06 §9.3，mock）</p>
      </div>
      <NButton round type="primary" @click="openCreate">+ 新增场景</NButton>
    </header>

    <p v-if="error" class="rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-xs text-[#B91C1C]">
      {{ error }}
    </p>

    <section class="rounded-[12px] border border-[#E5E7EB] bg-white p-4">
      <div v-if="loading" class="py-10 text-center text-sm text-[#667085]">加载中…</div>
      <n-data-table v-else :columns="columns" :data="scenes" :bordered="false" :pagination="{ pageSize: 10 }" />
    </section>

    <NModal v-model:show="showModal" :title="editingId == null ? '新增场景' : '编辑场景'">
      <div class="p-6">
        <NForm>
          <NFormItem label="标题">
            <NInput v-model:value="form.title" placeholder="场景标题" />
          </NFormItem>
          <NFormItem label="类型">
            <NSelect v-model:value="form.sceneType" :options="sceneTypes" />
          </NFormItem>
          <NFormItem label="难度">
            <NInputNumber v-model:value="form.difficulty" :min="1" :max="4" />
          </NFormItem>
        </NForm>
        <div class="mt-4 flex justify-end gap-2">
          <NButton round @click="showModal = false">取消</NButton>
          <NButton round type="primary" @click="save">保存</NButton>
        </div>
      </div>
    </NModal>
  </div>
</template>