<script setup lang="ts">
/**
 * 媒体库（docs/50 §6.1 第 5 条 + §10.3）。
 *
 * 媒体资产同样由 **Python 服务写**（单写方矩阵，§3.2），列表走 `opsApi.listMedia`、
 * 治理动作走 `opsApi.hideMedia`；控制台只做「隐藏 / 恢复」，不提供删除——媒体被帖子引用，
 * 物理删除会留下悬空引用（§6.1 只允许 ready / hidden / deleted 三态流转）。
 *
 * `public_id` 是运维与用户报障时唯一可对得上的标识，因此单独一列等宽显示 + 一键复制。
 *
 * ⚠️ 字段与筛选枚举按 `services/python/app/console/api/routes/library.py:206-322` 直读：
 * - `kind` 取值是 `image|video|avatar`（models/media.py:62 的 CHECK）——**没有 audio**，
 *   v1 的筛选下拉给了"音频"，选了必然空列表；
 * - `_media_view` **不返回** `width`/`height`/`duration_s`（库里那三列没被投影），
 *   所以"尺寸 / 时长"列无数据可显示，已改成 MIME 与体积。
 */
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NDataTable, NPagination, NSelect, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

import { opsApi } from '@/api'
import type { MediaAssetRow, MediaKind, MediaStatus } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { usePagedList } from '@/composables/usePagedList'
import { fmtBytes, fmtDateTime, fmtInt, fmtRelative } from '@/utils/format'
import MediaActionButtons from './MediaActionButtons.vue'

type Filters = {
  kind: string
  status: string
}

const message = useMessage()

const { items, total, page, pageCount, loading, error, errorCode, load, applyFilters, goPage } =
  usePagedList<MediaAssetRow, Filters>((q) => opsApi.listMedia(q), { kind: '', status: '' })

const kind = ref<string | null>(null)
const status = ref<string | null>(null)

// 同 SongsView：把 usePagedList 的 `{value:T[]}` 包成 computed，模板才能直接当数组用
const rows = computed(() => items.value)

const kindOptions = [
  { label: '图片', value: 'image' },
  { label: '视频', value: 'video' },
  { label: '头像', value: 'avatar' },
]

const statusOptions = [
  { label: '可用', value: 'ready' },
  { label: '已隐藏', value: 'hidden' },
  { label: '已删除', value: 'deleted' },
]

const KIND_LABEL: Record<MediaKind, string> = { image: '图片', video: '视频', avatar: '头像' }
const STATUS_LABEL: Record<MediaStatus, string> = {
  ready: '可用',
  hidden: '已隐藏',
  deleted: '已删除',
}

/**
 * StatusBadge 的 kind 映射表里没有 media 类目（该组件不在本次可改范围），
 * 故借用 publish 的色调语义并覆盖文案：ready≈已上架(绿)、hidden≈已下架(橙)、deleted≈草稿(灰)。
 */
const STATUS_TONE: Record<MediaStatus, { kind: string; value: string }> = {
  ready: { kind: 'publish', value: 'published' },
  hidden: { kind: 'publish', value: 'archived' },
  deleted: { kind: 'publish', value: 'draft' },
}

async function copyPublicId(publicId: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(publicId)
    message.success(`已复制 ${publicId}`)
  } catch {
    // 非安全上下文（http 非 localhost）下剪贴板不可用——明确报错，不静默失败
    message.error('复制失败：浏览器未开放剪贴板权限，请手动选择文本')
  }
}

const columns = computed<DataTableColumns<MediaAssetRow>>(() => [
  {
    title: '类型',
    key: 'kind',
    width: 90,
    render: (row) => h(StatusBadge, { kind: 'media', value: row.kind, label: KIND_LABEL[row.kind] }),
  },
  {
    title: 'public_id',
    key: 'public_id',
    minWidth: 260,
    render: (row) =>
      h('div', { class: 'flex items-center gap-2' }, [
        h('span', { class: 'c-mono' }, row.public_id),
        h(
          NButton,
          {
            size: 'tiny',
            text: true,
            title: '复制 public_id',
            'aria-label': `复制 ${row.public_id}`,
            onClick: () => void copyPublicId(row.public_id),
          },
          { default: () => '复制' },
        ),
      ]),
  },
  {
    title: '归属用户',
    key: 'owner_id',
    width: 120,
    render: (row) => h('span', { class: 'c-mono' }, `#${fmtInt(row.owner_id)}`),
  },
  {
    title: 'MIME',
    key: 'mime_type',
    width: 150,
    render: (row) => h('span', { class: 'c-mono' }, row.mime_type),
  },
  { title: '体积', key: 'size_bytes', width: 110, render: (row) => fmtBytes(row.size_bytes) },
  {
    title: '状态',
    key: 'status',
    width: 110,
    render: (row) => h(StatusBadge, { ...STATUS_TONE[row.status], label: STATUS_LABEL[row.status] }),
  },
  {
    title: '上传时间',
    key: 'created_at',
    width: 180,
    render: (row) =>
      h('div', [
        h('div', fmtDateTime(row.created_at)),
        h('div', { class: 'c-weak text-12px' }, fmtRelative(row.created_at)),
      ]),
  },
  {
    title: '操作',
    key: 'actions',
    width: 130,
    render: (row) => h(MediaActionButtons, { publicId: row.public_id, status: row.status, onDone: () => void load() }),
  },
])

function onKind(value: string | null): void {
  kind.value = value
  void applyFilters({ kind: value ?? '' })
}

function onStatus(value: string | null): void {
  status.value = value
  void applyFilters({ status: value ?? '' })
}

onMounted(() => void load())
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="媒体库"
      desc="媒体资产治理：隐藏违规资产或恢复误判；隐藏后该资产不再允许被内容引用，文件本身不删除。"
    />

    <div class="c-card">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <n-select
          :value="kind"
          class="w-32"
          :options="kindOptions"
          clearable
          placeholder="全部类型"
          @update:value="onKind"
        />
        <n-select
          :value="status"
          class="w-32"
          :options="statusOptions"
          clearable
          placeholder="全部状态"
          @update:value="onStatus"
        />
        <span class="c-weak text-12px">共 {{ fmtInt(total) }} 条</span>
      </div>

      <p class="c-weak text-12px mv-note">
        后端未提供尺寸与时长（`library.py:311` 的 `_media_view` 没有投影 width/height/duration_s），
        因此本表不显示该列——不拿 0 或占位符充数。需要逐条看清文件时可用响应里的 <code>url</code>。
      </p>

      <AsyncBlock
        :loading="loading"
        :error="error"
        :error-code="errorCode"
        :empty="rows.length === 0"
        empty-text="没有匹配的媒体资产"
        empty-hint="清空类型或状态筛选再试"
      >
        <n-data-table
          :columns="columns"
          :data="rows"
          :row-key="(row: MediaAssetRow) => row.public_id"
          :bordered="false"
          :single-line="false"
          :pagination="false"
          :scroll-x="1180"
          size="small"
        />
      </AsyncBlock>

      <div class="flex justify-end mt-4">
        <n-pagination :page="page" :page-count="pageCount" :page-slot="7" @update:page="goPage" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.mv-note {
  margin: 0 0 10px;
  line-height: 1.6;
}
.mv-note code {
  font-family: var(--vv-font-mono);
}
</style>
