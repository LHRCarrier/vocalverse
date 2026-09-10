<script setup lang="ts">
/**
 * 歌曲库（docs/50 §6.1 上架语义 + §10.2 端点）。
 *
 * 只做「看状态 + 上下架」：歌曲的增改删仍在既有 admin CRUD 里，控制台不提供物理删除
 * （§6.1 拍板：归档即软删）。下架对用户不生效这一缺口写进页面常驻提示（§15.2 G-2）。
 *
 * ⚠️ 没有关键词输入框：`ConsoleContentController.listSongs` 只接受 `page/page_size/status`
 * 三个参数（其余三个内容域的 `listXxx` 同样没有 `q`），传 `q` 会被 Spring 静默忽略
 * —— 那样框里输入什么都不会改变结果，是"看着能用其实没用"的假控件，故去掉并改成静态说明。
 */
import { computed, onMounted, ref } from 'vue'
import { NButton, NDataTable, NPagination, NSelect } from 'naive-ui'

import { consoleApi } from '@/api'
import type { SongRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import PermissionGate from '@/components/common/PermissionGate.vue'
import { usePagedList } from '@/composables/usePagedList'
import { fmtInt } from '@/utils/format'
import ConsumerGapNote from './ConsumerGapNote.vue'
import LrcEditorModal from './authoring/LrcEditorModal.vue'
import SongFormModal from './authoring/SongFormModal.vue'
import { songColumns } from './songsColumns'

/** 筛选条件与 `GET /content/songs` 的 query 同名；空串由 client 自动丢弃 */
type Filters = {
  status: string
}

/** 下架无用户侧消费者的缺口说明：页面常驻 + 确认框重复一遍（docs/50 §15.2 G-2） */
const CONSUMER_GAP = '注意：歌曲下架暂无用户侧消费者，学生端不会马上看不到这首歌（docs/50 §15.2 G-2）。'

const { items, total, page, pageCount, loading, error, errorCode, load, applyFilters, goPage } =
  usePagedList<SongRow, Filters>((q) => consoleApi.listSongs(q), { status: '' })

const status = ref<string | null>(null)

// usePagedList 把 items 标成 `{value:T[]}`（为支持外部赋值），该类型在模板里不会被当作
// Ref 解包，故包一层 computed——模板只认「顶层 Ref 自动解包」这一条规则
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
  songColumns({
    domain: 'song',
    publishPermission: 'content:song:publish',
    consumerNote: CONSUMER_GAP,
    onChanged: () => void load(),
    onEdit: (row) => openForm(row),
    onEditLrc: (row) => openLrc(row),
  }),
)

// ── 内容维护（新建 / 编辑 / 歌词） ─────────────────────────────────────────
//
// 编辑弹窗只吃**行数据**（`SongRow`）而不是自己拷一份：详情一律由弹窗里重新回读
// （`GET /content/songs/{id}`），因为列表行只有 6 个字段，拿它回填会把未展示的字段清空。
const formTarget = ref<SongRow | null>(null)
const showForm = ref(false)

const lrcTarget = ref<SongRow | null>(null)
const showLrc = ref(false)

function openForm(row: SongRow | null): void {
  formTarget.value = row
  showForm.value = true
}

function openLrc(row: SongRow): void {
  lrcTarget.value = row
  showLrc.value = true
}

onMounted(() => void load())
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="歌曲库"
      desc="查看歌曲上架状态并执行上架 / 下架；上架前服务端会做前置校验，缺 lrc 或参考旋律未就绪会逐字段报错。"
    />

    <ConsumerGapNote target="歌曲" />

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
        <PermissionGate code="content:song:write">
          <n-button class="ml-auto" size="small" type="primary" @click="openForm(null)">
            新建歌曲
          </n-button>
        </PermissionGate>
      </div>

      <AsyncBlock
        :loading="loading"
        :error="error"
        :error-code="errorCode"
        :empty="rows.length === 0"
        empty-text="没有匹配的歌曲"
        empty-hint="清空状态筛选，或改用其它页翻找"
      >
        <n-data-table
          :columns="columns"
          :data="rows"
          :row-key="(row: SongRow) => row.id"
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

    <SongFormModal v-model:show="showForm" :target="formTarget" @saved="() => void load()" />

    <LrcEditorModal
      v-if="lrcTarget"
      v-model:show="showLrc"
      :song-id="lrcTarget.id"
      :song-title="lrcTarget.title"
      :pitch-ref-status="lrcTarget.pitchRefStatus"
      @saved="() => void load()"
    />
  </div>
</template>
