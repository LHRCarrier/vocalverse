<script setup lang="ts">
/**
 * 书籍（docs/50 §6.1 / §10.3）。
 *
 * ⚠️ 书籍是 **Python 服务写**的数据（单写方矩阵，§3.2），所以列表走 `opsApi.listBooks`、
 * 上下架走 `opsApi.publishBook`，而不是 Java 侧的 `consoleApi.publish`——两边端点都在
 * `/api/v1/console/library/**` 下，权限码同为 `content:book:publish`。
 *
 * ⚠️ 字段按 `services/python/app/console/api/routes/library.py:285-295` 直读：
 * 列表只有 `chapter_count`（**全部章节数**），**没有"已上架章节数"**——
 * v1 页面读的 `publishedChapters` 后端不存在，所以"已上架 / 总数"这个预检在这里做不了。
 * 想做逐章预检只能进 `GET /library/books/{id}/chapters`（本页不再为每行多发一次请求）；
 * 上架时若章节未齐，服务端仍会以 46011 + `data.violations[]` 逐字段报回来。
 */
import { computed, h, onMounted, ref } from 'vue'
import { NDataTable, NInput, NPagination, NSelect } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

import { opsApi } from '@/api'
import type { LibraryBookRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { debounce } from '@/composables/useAsync'
import { usePagedList } from '@/composables/usePagedList'
import { fmtDateTime, fmtInt, fmtRelative } from '@/utils/format'
import PublishActionButton from './PublishActionButton.vue'

type Filters = {
  q: string
  status: string
}

const { items, total, page, pageCount, loading, error, errorCode, load, applyFilters, goPage } =
  usePagedList<LibraryBookRow, Filters>((q) => opsApi.listBooks(q), { q: '', status: '' })

const keyword = ref('')
const status = ref<string | null>(null)

// 同 SongsView：把 usePagedList 的 `{value:T[]}` 包成 computed，模板才能直接当数组用
const rows = computed(() => items.value)

const statusOptions = [
  { label: '草稿', value: 'draft' },
  { label: '已上架', value: 'published' },
  { label: '已下架', value: 'archived' },
]

const search = debounce((value: string) => void applyFilters({ q: value.trim() }), 300)

function onKeyword(value: string): void {
  keyword.value = value
  search(value)
}

function onStatus(value: string | null): void {
  status.value = value
  void applyFilters({ status: value ?? '' })
}

/** 章节数：后端只给"总章节数"，查一次章节清单才能知道逐章状态——列表页不做 N 次请求 */
function renderChapters(row: LibraryBookRow) {
  return [
    h('span', { class: 'c-num' }, fmtInt(row.chapter_count)),
    h('span', { class: 'c-weak text-12px ml-2' }, '后端未提供已上架章节数'),
  ]
}

const columns = computed<DataTableColumns<LibraryBookRow>>(() => [
  { title: '标题', key: 'title', minWidth: 220, ellipsis: { tooltip: true } },
  { title: '作者', key: 'author', width: 160, ellipsis: { tooltip: true } },
  { title: '等级', key: 'level', width: 78, render: (row) => h('span', { class: 'c-mono' }, row.level) },
  { title: '章节数', key: 'chapters', width: 190, render: renderChapters },
  { title: '词数', key: 'word_count', width: 96, render: (row) => h('span', { class: 'c-num' }, fmtInt(row.word_count)) },
  {
    title: '状态',
    key: 'status',
    width: 110,
    render: (row) => h(StatusBadge, { kind: 'publish', value: row.status }),
  },
  {
    title: '更新时间',
    key: 'updated_at',
    width: 180,
    render: (row) =>
      h('div', [
        h('div', fmtDateTime(row.updated_at)),
        h('div', { class: 'c-weak text-12px' }, fmtRelative(row.updated_at)),
      ]),
  },
  {
    title: '操作',
    key: 'actions',
    width: 120,
    render: (row) =>
      h(PublishActionButton, {
        id: row.id,
        title: row.title,
        status: row.status,
        permission: 'content:book:publish',
        consumerNote: '书籍上架要求每一章都已上架（docs/50 §6.1）；有未上架章节时本操作会被 46011 拦下。',
        submit: (id, next) => opsApi.publishBook(id, next),
        onDone: () => void load(),
      }),
  },
])

onMounted(() => void load())
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="书籍"
      desc="书籍与章节由 Python 服务写入；本页只做上架 / 下架，上架要求全部章节已上架（未齐时服务端 46011 逐字段报回）。"
    />

    <div class="c-card">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <n-input :value="keyword" class="w-64" clearable placeholder="搜索书名" @update:value="onKeyword" />
        <n-select
          :value="status"
          class="w-36"
          :options="statusOptions"
          clearable
          placeholder="全部状态"
          @update:value="onStatus"
        />
        <span class="c-weak text-12px">共 {{ fmtInt(total) }} 条</span>
      </div>

      <AsyncBlock
        :loading="loading"
        :error="error"
        :error-code="errorCode"
        :empty="rows.length === 0"
        empty-text="没有匹配的书籍"
        empty-hint="换个关键词，或清空状态筛选"
      >
        <n-data-table
          :columns="columns"
          :data="rows"
          :row-key="(row: LibraryBookRow) => row.id"
          :bordered="false"
          :single-line="false"
          :pagination="false"
          size="small"
        />
      </AsyncBlock>

      <div class="flex justify-end mt-4">
        <n-pagination :page="page" :page-count="pageCount" :page-slot="7" @update:page="goPage" />
      </div>
    </div>
  </div>
</template>
