<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { NButton, NInput, NModal, NTag } from 'naive-ui'

import type { DataTableColumns } from 'naive-ui'

import { fetchAdminSongLrc, fetchSongs, toggleSong, updateAdminSongLrc } from '@/api/admin'
import type { AdminSong } from '@/api/m3-types'

const songs = ref<AdminSong[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const showLrc = ref(false)
const editingId = ref<number | null>(null)
const lrcText = ref('')

const columns: DataTableColumns<AdminSong> = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '标题', key: 'title' },
  { title: '歌手', key: 'artist' },
  { title: '难度', key: 'difficulty', width: 80 },
  {
    title: '歌词',
    key: 'hasLrc',
    width: 90,
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.hasLrc ? 'success' : 'default', bordered: false },
        { default: () => (row.hasLrc ? '已录入' : '无') },
      ),
  },
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
    width: 180,
    render: (row) => [
      h(NButton, { size: 'small', quaternary: true, onClick: () => openLrc(row) }, { default: () => '编辑 LRC' }),
      h(
        NButton,
        { size: 'small', quaternary: true, type: row.status === 'on' ? 'warning' : 'primary', onClick: () => onToggle(row) },
        { default: () => (row.status === 'on' ? '下架' : '上架') },
      ),
    ],
  },
]

async function openLrc(row: AdminSong) {
  editingId.value = row.id
  try {
    lrcText.value = await fetchAdminSongLrc(row.id)
    showLrc.value = true
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function saveLrc() {
  if (editingId.value == null) return
  try {
    await updateAdminSongLrc(editingId.value, lrcText.value)
    showLrc.value = false
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function onToggle(row: AdminSong) {
  try {
    songs.value = await toggleSong(row.id)
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(async () => {
  try {
    songs.value = await fetchSongs()
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
      <h1 class="mb-2 text-xl font-bold">歌曲库</h1>
      <p class="text-sm text-[#667085]">歌曲 + LRC 词库编辑（docs/06 §9.3，mock）</p>
    </header>

    <p v-if="error" class="rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-xs text-[#B91C1C]">
      {{ error }}
    </p>

    <section class="rounded-[12px] border border-[#E5E7EB] bg-white p-4">
      <div v-if="loading" class="py-10 text-center text-sm text-[#667085]">加载中…</div>
      <n-data-table v-else :columns="columns" :data="songs" :bordered="false" :pagination="{ pageSize: 10 }" />
    </section>

    <NModal v-model:show="showLrc" title="编辑 LRC 歌词">
      <div class="p-6">
        <NInput
          v-model:value="lrcText"
          type="textarea"
          :rows="8"
          placeholder="逐行填写歌词（每行一句）"
        />
        <div class="mt-4 flex justify-end gap-2">
          <NButton round @click="showLrc = false">取消</NButton>
          <NButton round type="primary" @click="saveLrc">保存</NButton>
        </div>
      </div>
    </NModal>
  </div>
</template>