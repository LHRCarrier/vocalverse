<script setup lang="ts">
/**
 * 题目新建 / 编辑弹窗（`POST /content/questions` · `PUT /content/questions/{id}`）。
 *
 * 与其它三个内容弹窗的**关键差异**（不是风格问题，是接口形状问题）：
 * 1. **创建与编辑是两个不同的请求体**：`QuestionUpsert`（含身份字段 `examRevision`/`itemIndex`）
 *    用于新建；`QuestionPatch`（只有 `prompt`/`referenceAnswer`/`status`）用于编辑 ——
 *    后端**不接受**改身份字段（改题号等于换一道题，会让历史作答对不上）。
 *    所以编辑态下这两个输入框是禁用的，并写明原因，而不是让运营改完再吃一个 46007。
 * 2. **题库只有两态**（`published|archived`，无 `draft`）→ 用 `QUESTION_STATUS_OPTIONS`；
 *    同理题库没有 `content:question:publish` 权限码，页面上也就没有上下架按钮。
 * 3. `itemIndex` 在同版本内必须唯一：服务端 `createQuestion` 显式查重并以 **46007** 拒绝
 *    （不是 Bean Validation），前端无法预判其它题号，所以只在提示里说清规则。
 */
import { computed, ref, watch } from 'vue'
import { NInput, NSelect } from 'naive-ui'

import { consoleApi } from '@/api'
import type { QuestionRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import { describeActionError } from '@/views/content/actionReason'
import ContentFormModal from './ContentFormModal.vue'
import FormField from './FormField.vue'
import { emptyQuestionForm, validateQuestionForm } from './contentFormModel'
import { fillQuestionForm, toQuestionPatch, toQuestionUpsert } from './contentFormPayload'
import type { QuestionForm } from './contentFormTypes'
import { QUESTION_KIND_OPTIONS, QUESTION_STATUS_OPTIONS } from './formMeta'
import { useContentForm } from './useContentForm'

const props = defineProps<{
  /** null = 新建；非 null 只用它的 `id` 与题号（详情一律回读） */
  target: QuestionRow | null
}>()

const show = defineModel<boolean>('show', { required: true })
const emit = defineEmits<{ saved: [] }>()

const form = ref<QuestionForm>(emptyQuestionForm())
const original = ref<QuestionForm | null>(null)
const loading = ref(false)
const loadError = ref<string | null>(null)
const loadErrorCode = ref<number | null>(null)

const { submitting, errors, failure, clearField, run } = useContentForm()

const isEdit = computed(() => props.target !== null)
const title = computed(() =>
  isEdit.value
    ? `编辑题目 · 第 ${props.target?.examRevision ?? '?'} 卷 / ${props.target?.itemIndex ?? '?'} 题`
    : '新建题目',
)
const ready = computed(() => !isEdit.value || original.value !== null)

function editText(key: keyof QuestionForm, value: string): void {
  form.value = { ...form.value, [key]: value }
  clearField(key)
}

/** 回读单条（列表行不含参考答案，编辑必须回读，否则保存会把参考答案清空） */
async function load(): Promise<void> {
  form.value = emptyQuestionForm()
  original.value = null
  loadError.value = null
  loadErrorCode.value = null
  if (!props.target) return
  loading.value = true
  try {
    const detail = await consoleApi.getQuestion(props.target.id)
    form.value = fillQuestionForm(detail)
    original.value = { ...form.value }
  } catch (err) {
    const described = describeActionError(err)
    loadError.value = described.message
    loadErrorCode.value = described.code
  } finally {
    loading.value = false
  }
}

watch(show, (open) => {
  if (open) void load()
})

async function onSubmit(): Promise<void> {
  await run({
    validate: () => validateQuestionForm(form.value),
    submit: () =>
      props.target
        ? consoleApi.updateQuestion(props.target.id, toQuestionPatch(form.value))
        : consoleApi.createQuestion(toQuestionUpsert(form.value)),
    onSuccess: () => {
      show.value = false
      emit('saved')
    },
  })
}
</script>

<template>
  <ContentFormModal
    v-model:show="show"
    :title="title"
    :submitting="submitting"
    :failure="failure"
    :has-field-errors="Object.keys(errors).length > 0"
    :submit-text="isEdit ? '保存' : '创建'"
    @submit="onSubmit"
  >
    <AsyncBlock
      :loading="loading"
      :error="loadError"
      :error-code="loadErrorCode"
      :empty="!ready"
      empty-text="正在读取题目详情…（列表行不含参考答案，编辑前必须回读）"
      :min-height="120"
    >
      <FormField
        label="试卷版本"
        required
        :error="errors.examRevision"
        :hint="isEdit ? '编辑时不可改：后端 QuestionPatch 不接受身份字段（改版本等于换一套卷）' : '整数，与题号共同定位一道题（@Min(1)）'"
      >
        <n-input
          :value="form.examRevision"
          :disabled="isEdit"
          @update:value="editText('examRevision', $event)"
        />
      </FormField>

      <FormField
        label="题号"
        required
        :error="errors.itemIndex"
        :hint="isEdit ? '编辑时不可改：后端 QuestionPatch 不接受身份字段（改题号等于换一道题）' : '同一版本内必须唯一，撞车以 46007 拒绝'"
      >
        <n-input
          :value="form.itemIndex"
          :disabled="isEdit"
          @update:value="editText('itemIndex', $event)"
        />
      </FormField>

      <FormField label="题目类型" required :error="errors.kind" hint="read = 朗读题（走跟读评分）；qa = 问答题">
        <n-select
          :value="form.kind"
          :options="[...QUESTION_KIND_OPTIONS]"
          placeholder="请选择"
          @update:value="editText('kind', $event)"
        />
      </FormField>

      <FormField label="题干" required :error="errors.prompt">
        <n-input
          :value="form.prompt"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          @update:value="editText('prompt', $event)"
        />
      </FormField>

      <FormField label="参考答案" :error="errors.referenceAnswer" hint="问答题的评分参照；朗读题可留空">
        <n-input
          :value="form.referenceAnswer"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          @update:value="editText('referenceAnswer', $event)"
        />
      </FormField>

      <FormField label="状态" :error="errors.status" hint="题库只有两态：启用 / 归档（没有草稿态）">
        <n-select
          :value="form.status"
          :options="[...QUESTION_STATUS_OPTIONS]"
          @update:value="editText('status', $event)"
        />
      </FormField>
    </AsyncBlock>
  </ContentFormModal>
</template>
