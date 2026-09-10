<script setup lang="ts">
/**
 * 场景库（docs/50 §6.1 上架语义 + §10.2 端点）。
 *
 * 与歌曲 / 听力同构；上架前置校验为「opening_line + 语言点 ≥ 3 条」（§6.1），
 * 失败同样是 46011 + 字段级 violations[]——运营一次看到缺什么，不用逐条试。
 * 场景不在 §15.2 G-2 缺口范围内，故不加缺口提示。
 *
 * ⚠️ `sceneType` 筛选是后端**真实支持**的参数（`ConsoleContentController.listScenarios`），
 * 下拉选项从**已加载的行**里收集：Java 侧没有"场景类型目录"端点，
 * 因此这里不编造一份类型清单（编了就会与库里实际存在的类型不一致）。
 */
import { computed, onMounted, ref } from 'vue'
import { NDataTable, NPagination, NSelect } from 'naive-ui'

import { consoleApi } from '@/api'
import type { ScenarioRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { usePagedList } from '@/composables/usePagedList'
import { fmtInt } from '@/utils/format'
import { scenarioColumns } from './scenarioColumns'

type Filters = {
  status: string
  sceneType: string
}

const { items, total, page, pageCount, loading, error, errorCode, load, applyFilters, goPage } =
  usePagedList<ScenarioRow, Filters>((q) => consoleApi.listScenarios(q), {
    status: '',
    sceneType: '',
  })

const status = ref<string | null>(null)
const sceneType = ref<string | null>(null)

// 同 SongsView：把 usePagedList 的 `{value:T[]}` 包成 computed，模板才能直接当数组用
const rows = computed(() => items.value)

const statusOptions = [
  { label: '草稿', value: 'draft' },
  { label: '已上架', value: 'published' },
  { label: '已下架', value: 'archived' },
]

/** 下拉里出现过的场景类型（含当前筛选项，否则选中后会被自己的过滤结果挤掉） */
const sceneTypeOptions = computed(() => {
  const seen = new Set<string>()
  for (const row of rows.value) if (row.sceneType) seen.add(row.sceneType)
  if (sceneType.value) seen.add(sceneType.value)
  return [...seen].map((value) => ({ label: value, value }))
})

function onStatus(value: string | null): void {
  status.value = value
  void applyFilters({ status: value ?? '' })
}

function onSceneType(value: string | null): void {
  sceneType.value = value
  void applyFilters({ sceneType: value ?? '' })
}

const columns = computed(() =>
  scenarioColumns({
    domain: 'scenario',
    publishPermission: 'content:scenario:publish',
    onChanged: () => void load(),
  }),
)

onMounted(() => void load())
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="场景库"
      desc="管理对话场景的上架状态；上架要求开场白与语言点齐备（语言点少于 3 条会被服务端拦下）。"
    />

    <div class="c-card">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <n-select
          :value="sceneType"
          class="w-44"
          :options="sceneTypeOptions"
          clearable
          filterable
          placeholder="全部场景类型"
          @update:value="onSceneType"
        />
        <n-select
          :value="status"
          class="w-36"
          :options="statusOptions"
          clearable
          placeholder="全部状态"
          @update:value="onStatus"
        />
        <span class="c-weak text-12px">共 {{ fmtInt(total) }} 条</span>
        <span class="c-weak text-12px">场景类型选项来自当前已加载的行（服务端没有类型目录接口）。</span>
      </div>

      <AsyncBlock
        :loading="loading"
        :error="error"
        :error-code="errorCode"
        :empty="rows.length === 0"
        empty-text="没有匹配的场景"
        empty-hint="清空类型或状态筛选再试"
      >
        <n-data-table
          :columns="columns"
          :data="rows"
          :row-key="(row: ScenarioRow) => row.id"
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
