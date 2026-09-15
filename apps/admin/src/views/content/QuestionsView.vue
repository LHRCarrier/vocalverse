<script setup lang="ts">
/**
 * 题库（docs/50 §6.1 内容域 + §10.2 端点）。
 *
 * 为什么这一页之前**完全不存在**（2026-09-10 补）：后端 `content/questions` 的读写端点
 * 从控制台模块第一天起就齐了（`ConsoleContentWriteController` 的 POST/PUT/DELETE），
 * 权限码 `content:question:read/write` 也在 `PermissionCatalog` 里登记着 —— 但前端没有任何
 * 页面或路由用它。于是"题库可管理"这句话在界面上不成立：运营拿不到入口，
 * 而权限码成了**发不出去也测不到**的装饰。这正是 `docs/51 §1.7` 那条退役原则的另一面：
 * **只删入口不算完，还要确认每个能力都有新的入口**。
 *
 * 与歌曲库/听力素材的三处差异（不是偷懒，是接口语义如此）：
 * 1. 筛选少一个 `status` 之外的维度；服务端 `listQuestions` 支持
 *    `examRevision` / `itemIndex` / `kind` / `status` / 分页，这里**只暴露 status + kind**
 *    （另两个是精确定位用的，运营日常不用，多一个空框就多一处"看着能用其实没用"）；
 * 2. 没有上下架按钮（无 publish 权限码，题库只有启用/归档两态），归档走 `QuestionArchiveButton`；
 * 3. 有 `draft` 的域在列表上能看出"没做完"，题库没有草稿态 —— 建出来就是启用，
 *    所以新建弹窗的默认状态是 `published`（与 `createQuestion` 的服务端默认一致）。
 */
import { computed, onMounted, ref } from 'vue'
import { NButton, NDataTable, NPagination, NSelect } from 'naive-ui'

import { consoleApi } from '@/api'
import type { QuestionRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import PermissionGate from '@/components/common/PermissionGate.vue'
import { usePagedList } from '@/composables/usePagedList'
import { fmtInt } from '@/utils/format'
import QuestionFormModal from './authoring/QuestionFormModal.vue'
import { QUESTION_KIND_OPTIONS, QUESTION_STATUS_OPTIONS } from './authoring/formMeta'
import { questionColumns } from './questionColumns'

/** 筛选条件与 `GET /content/questions` 的 query 同名；空串由 client 自动丢弃 */
type Filters = {
  status: string
  kind: string
}

const { items, total, page, pageCount, loading, error, errorCode, load, applyFilters, goPage } =
  usePagedList<QuestionRow, Filters>((q) => consoleApi.listQuestions(q), { status: '', kind: '' })

const status = ref<string | null>(null)
const kind = ref<string | null>(null)

const rows = computed(() => items.value)

function onStatus(value: string | null): void {
  status.value = value
  void applyFilters({ status: value ?? '', kind: kind.value ?? '' })
}

function onKind(value: string | null): void {
  kind.value = value
  void applyFilters({ status: status.value ?? '', kind: value ?? '' })
}

const formTarget = ref<QuestionRow | null>(null)
const showForm = ref(false)

function openForm(row: QuestionRow | null): void {
  formTarget.value = row
  showForm.value = true
}

const columns = computed(() =>
  questionColumns({
    onEdit: (row) => openForm(row),
    onChanged: () => void load(),
  }),
)

onMounted(() => void load())
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="题库"
      desc="试卷题目的启用与归档；题目按「试卷版本 + 题号」定位，同一版本内题号不可重复。"
    />

    <div class="c-card">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <n-select
          :value="status"
          class="w-36"
          :options="[...QUESTION_STATUS_OPTIONS]"
          clearable
          placeholder="全部状态"
          @update:value="onStatus"
        />
        <n-select
          :value="kind"
          class="w-36"
          :options="[...QUESTION_KIND_OPTIONS]"
          clearable
          placeholder="全部题型"
          @update:value="onKind"
        />
        <span class="c-weak text-12px">共 {{ fmtInt(total) }} 条</span>
        <span class="c-weak text-12px">
          服务端可按试卷版本 / 题号精确定位，但那两个维度日常不用，故不在这里摆输入框。
        </span>
        <PermissionGate code="content:question:write">
          <n-button class="ml-auto" size="small" type="primary" @click="openForm(null)">
            新建题目
          </n-button>
        </PermissionGate>
      </div>

      <AsyncBlock
        :loading="loading"
        :error="error"
        :error-code="errorCode"
        :empty="rows.length === 0"
        empty-text="没有匹配的题目"
        empty-hint="清空筛选条件，或改用其它页翻找"
      >
        <n-data-table
          :columns="columns"
          :data="rows"
          :row-key="(row: QuestionRow) => row.id"
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

    <QuestionFormModal v-model:show="showForm" :target="formTarget" @saved="() => void load()" />
  </div>
</template>
