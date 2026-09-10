<script setup lang="ts">
/**
 * 听力素材（docs/50 §6.1 上架语义 + §10.2 端点）。
 *
 * 与歌曲库同构（域换 `listening`、权限换 `content:listening:publish`）；
 * 上架前置校验为「audio_url + transcript 非空」，失败走 46011 + data.violations[]（§6.1）。
 * 同样受 §15.2 G-2 缺口约束：下架暂无用户侧消费者。
 *
 * ⚠️ 行字段来自 `ConsoleContentController.MaterialRow`：`hasTranscript` 是布尔位（不是文本），
 * 没有 `meta` 之类的前端自造字段。
 */
import { computed, onMounted, ref } from 'vue'
import { NButton, NDataTable, NPagination, NSelect } from 'naive-ui'

import { consoleApi } from '@/api'
import type { MaterialRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import PermissionGate from '@/components/common/PermissionGate.vue'
import { usePagedList } from '@/composables/usePagedList'
import { fmtInt } from '@/utils/format'
import ConsumerGapNote from './ConsumerGapNote.vue'
import MaterialFormModal from './authoring/MaterialFormModal.vue'
import { materialColumns } from './listeningColumns'

type Filters = {
  status: string
}

const CONSUMER_GAP = '注意：听力素材下架暂无用户侧消费者，学生端不会马上看不到这条素材（docs/50 §15.2 G-2）。'

const { items, total, page, pageCount, loading, error, errorCode, load, applyFilters, goPage } =
  usePagedList<MaterialRow, Filters>((q) => consoleApi.listMaterials(q), { status: '' })

const status = ref<string | null>(null)

// 同 SongsView：把 usePagedList 的 `{value:T[]}` 包成 computed，模板才能直接当数组用
const rows = computed(() => items.value)

const statusOptions = [
  { label: '草稿', value: 'draft' },
  { label: '已上架', value: 'published' },
  { label: '已下架', value: 'archived' },
]

function onStatus(value: string | null): void {
  status.value = value
  void applyFilters({ status: value ?? '' })
}

const columns = computed(() =>
  materialColumns({
    domain: 'listening',
    publishPermission: 'content:listening:publish',
    consumerNote: CONSUMER_GAP,
    onChanged: () => void load(),
    onEdit: (row) => openForm(row),
  }),
)

// ── 内容维护（新建 / 编辑） ───────────────────────────────────────────────
// 列表行只有 `hasTranscript` 布尔位（服务端不把转写原文放进列表），
// 所以弹窗内部**必须**重新回读单条 —— 拿列表行回填会把已有转写清成空串。
const formTarget = ref<MaterialRow | null>(null)
const showForm = ref(false)

function openForm(row: MaterialRow | null): void {
  formTarget.value = row
  showForm.value = true
}

onMounted(() => void load())
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="听力素材"
      desc="管理听力素材的上架状态；上架要求音频与文本（transcript）齐备，缺失项由服务端逐字段返回。"
    />

    <ConsumerGapNote target="听力素材" />

    <div class="c-card">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <n-select
          :value="status"
          class="w-36"
          :options="statusOptions"
          clearable
          placeholder="全部状态"
          @update:value="onStatus"
        />
        <span class="c-weak text-12px">共 {{ fmtInt(total) }} 条</span>
        <span class="c-weak text-12px">服务端该接口只支持按状态筛选与分页，没有关键词搜索。</span>
        <PermissionGate code="content:listening:write">
          <n-button class="ml-auto" size="small" type="primary" @click="openForm(null)">
            新建听力素材
          </n-button>
        </PermissionGate>
      </div>

      <AsyncBlock
        :loading="loading"
        :error="error"
        :error-code="errorCode"
        :empty="rows.length === 0"
        empty-text="没有匹配的听力素材"
        empty-hint="清空状态筛选，或改用其它页翻找"
      >
        <n-data-table
          :columns="columns"
          :data="rows"
          :row-key="(row: MaterialRow) => row.id"
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

    <MaterialFormModal v-model:show="showForm" :target="formTarget" @saved="() => void load()" />
  </div>
</template>
