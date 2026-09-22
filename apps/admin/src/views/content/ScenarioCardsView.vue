<script setup lang="ts">
/**
 * 酒馆场景卡（docs/52 §12.1）。
 *
 * ⚠️ 场景卡是 **Python 服务写**的数据（`/api/v1/console/trpg/cards/**`），故走 `opsApi.*`
 * 而不是 Java 侧 `consoleApi.publish`；权限码 `content:scenario:{read,write,publish}`。
 *
 * 三种来源路径：
 * 1. 手工新建/编辑 → 保存为草稿 → 上架（上架校验失败服务端回 46011 + violations）；
 * 2. 「随机生成」→ 服务端 LLM 出草稿（不落库）→ 预填表单 → 人工修订 → 保存；
 * 3. 用户私有卡不经本页（App 内自管，owner_user_id 非空不列）。
 */
import { computed, h, onMounted, ref } from 'vue'
import {
  NButton,
  NDataTable,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NPagination,
  NSelect,
  useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

import { opsApi } from '@/api'
import type { ScenarioCardRow, ScenarioCardUpsert } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { debounce } from '@/composables/useAsync'
import { usePagedList } from '@/composables/usePagedList'
import { fmtDateTime } from '@/utils/format'
import PublishActionButton from './PublishActionButton.vue'

type Filters = { q: string; status: string }

const message = useMessage()
const { items, total, page, pageCount, loading, error, errorCode, load, applyFilters, goPage } =
  usePagedList<ScenarioCardRow, Filters>((q) => opsApi.listScenarioCards(q), { q: '', status: '' })

const rows = computed(() => items.value)
const keyword = ref('')
const status = ref<string | null>(null)

const statusOptions = [
  { label: '草稿', value: 'draft' },
  { label: '已上架', value: 'published' },
  { label: '已下架', value: 'archived' },
]

const search = debounce((value: string) => void applyFilters({ q: value.trim() }), 300)
const onKeyword = (value: string) => {
  keyword.value = value
  search(value)
}
const onStatus = (value: string | null) => {
  status.value = value
  void applyFilters({ status: value ?? '' })
}

/* ---------------- 编辑弹窗 ---------------- */
const editorOpen = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const generating = ref(false)
const genKeywords = ref('')

const form = ref<ScenarioCardUpsert>({
  title: '',
  summary: '',
  language: 'zh',
  tags: [],
  scene: '',
  opening_line: '',
  template: { pc_name: '主角', pc: {}, facts: [], tasks: [], clues: [] },
})
const tagsText = ref('')
const templateText = ref('{}')

function openCreate(): void {
  editingId.value = null
  form.value = {
    title: '',
    summary: '',
    language: 'zh',
    tags: [],
    scene: '',
    opening_line: '',
    template: { pc_name: '主角', pc: {}, facts: [], tasks: [], clues: [] },
  }
  tagsText.value = ''
  templateText.value = JSON.stringify(form.value.template, null, 2)
  genKeywords.value = ''
  editorOpen.value = true
}

function openEdit(row: ScenarioCardRow): void {
  editingId.value = row.id
  form.value = {
    title: row.title,
    summary: row.summary ?? '',
    language: row.language,
    tags: row.tags ?? [],
    scene: row.scene ?? '',
    opening_line: row.opening_line ?? '',
    template: row.template ?? {},
  }
  tagsText.value = (row.tags ?? []).join('，')
  templateText.value = JSON.stringify(row.template ?? {}, null, 2)
  genKeywords.value = row.keywords ?? ''
  editorOpen.value = true
}

function parseTags(): string[] {
  return tagsText.value
    .split(/[,，;；\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 6)
}

function parseTemplate(): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(templateText.value || '{}')
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

async function save(): Promise<void> {
  const template = parseTemplate()
  if (template === null) {
    message.error('模板 JSON 解析失败，请检查格式')
    return
  }
  const body: ScenarioCardUpsert = {
    ...form.value,
    tags: parseTags(),
    template,
  }
  saving.value = true
  try {
    if (editingId.value === null) {
      await opsApi.createScenarioCard(body)
      message.success('已保存为草稿，可在列表中上架')
    } else {
      await opsApi.updateScenarioCard(editingId.value, body)
      message.success('已保存')
    }
    editorOpen.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

async function generate(): Promise<void> {
  generating.value = true
  try {
    const draft = await opsApi.generateScenarioCard({
      keywords: genKeywords.value.trim() || undefined,
      lang: form.value.language ?? 'zh',
    })
    form.value = { ...form.value, ...draft }
    tagsText.value = (draft.tags ?? []).join('，')
    templateText.value = JSON.stringify(draft.template ?? {}, null, 2)
    message.success('已生成草稿，请人工复核后保存')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    generating.value = false
  }
}

const columns = computed<DataTableColumns<ScenarioCardRow>>(() => [
  { title: '标题', key: 'title', minWidth: 180, ellipsis: { tooltip: true } },
  { title: '场景', key: 'scene', width: 130, ellipsis: { tooltip: true } },
  {
    title: '语言',
    key: 'language',
    width: 76,
    render: (row) => h('span', { class: 'c-mono' }, row.language === 'en' ? 'EN' : '中文'),
  },
  {
    title: '标签',
    key: 'tags',
    width: 150,
    render: (row) => h('span', { class: 'c-weak text-12px' }, (row.tags ?? []).join(' · ') || '—'),
  },
  {
    title: '来源',
    key: 'generated_by',
    width: 92,
    render: (row) => h('span', { class: 'c-weak text-12px' }, row.generated_by === 'llm' ? 'LLM' : '手工'),
  },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render: (row) => h(StatusBadge, { kind: 'publish', value: row.status }),
  },
  { title: '更新时间', key: 'created_at', width: 170, render: (row) => h('span', fmtDateTime(row.created_at)) },
  {
    title: '操作',
    key: 'actions',
    width: 170,
    render: (row) =>
      h('div', { class: 'flex gap-2' }, [
        h(
          NButton,
          { size: 'small', quaternary: true, onClick: () => openEdit(row) },
          { default: () => '编辑' },
        ),
        h(PublishActionButton, {
          id: row.id,
          title: row.title,
          status: row.status,
          permission: 'content:scenario:publish',
          consumerNote: '上架后所有用户在酒馆开局引导里可选（docs/52 §12.1）。',
          submit: (id, next) => opsApi.publishScenarioCard(id, next),
          onDone: () => void load(),
        }),
      ]),
  },
])

onMounted(() => void load())
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="场景卡"
      desc="酒馆（TRPG）开局模板：平台固定卡上架后所有用户可选；支持「随机生成」由 LLM 起草后人工修订（docs/52 §12.1）。"
    >
      <template #actions>
        <n-button type="primary" @click="openCreate">新建卡片</n-button>
      </template>
    </PageHeader>

    <div class="c-card">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <n-input :value="keyword" class="w-64" clearable placeholder="搜索标题" @update:value="onKeyword" />
        <n-select
          :value="status"
          class="w-36"
          :options="statusOptions"
          clearable
          placeholder="全部状态"
          @update:value="onStatus"
        />
        <span class="c-weak text-12px">共 {{ total }} 条</span>
      </div>

      <AsyncBlock
        :loading="loading"
        :error="error"
        :error-code="errorCode"
        :empty="rows.length === 0"
        empty-text="还没有场景卡"
        empty-hint="点右上角「新建卡片」，或先用「随机生成」让 LLM 起草"
      >
        <n-data-table
          :columns="columns"
          :data="rows"
          :row-key="(row: ScenarioCardRow) => row.id"
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

    <n-modal
      v-model:show="editorOpen"
      preset="card"
      class="w-720px max-w-92vw"
      :title="editingId === null ? '新建场景卡' : '编辑场景卡'"
      :mask-closable="false"
    >
      <div class="flex items-center gap-2 mb-4">
        <n-input
          v-model:value="genKeywords"
          class="flex-1"
          clearable
          placeholder="随机生成：可选主题关键词（留空 = 主题池轮换），如「海盗 灯塔 幽灵船」"
        />
        <n-button :loading="generating" @click="generate">随机生成</n-button>
      </div>

      <n-form label-placement="top" size="small">
        <n-form-item label="标题（必填，≤60 字）">
          <n-input v-model:value="form.title" maxlength="60" show-count />
        </n-form-item>
        <n-form-item label="一句话简介">
          <n-input v-model:value="form.summary" maxlength="300" />
        </n-form-item>
        <div class="grid grid-cols-3 gap-3">
          <n-form-item label="语言">
            <n-select
              v-model:value="form.language"
              :options="[
                { label: '中文', value: 'zh' },
                { label: 'English', value: 'en' },
              ]"
            />
          </n-form-item>
          <n-form-item label="起始场景">
            <n-input v-model:value="form.scene" maxlength="40" placeholder="酒馆 / 灯塔…" />
          </n-form-item>
          <n-form-item label="标签（逗号分隔，≤6）">
            <n-input v-model:value="tagsText" placeholder="悬疑，小镇" />
          </n-form-item>
        </div>
        <n-form-item label="开场叙述（必填；将作为 DM 的第一条消息，支持换行）">
          <n-input
            v-model:value="form.opening_line"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            maxlength="600"
            show-count
          />
        </n-form-item>
        <n-form-item label="开局模板（JSON：pc / facts / tasks / clues；服务端会做白名单校验）">
          <n-input v-model:value="templateText" type="textarea" :autosize="{ minRows: 8, maxRows: 16 }" />
        </n-form-item>
      </n-form>

      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="editorOpen = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>
