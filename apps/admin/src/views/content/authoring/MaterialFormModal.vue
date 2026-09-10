<script setup lang="ts">
/**
 * 听力素材新建 / 编辑弹窗（`POST|PUT /content/listening-materials`）。
 *
 * 与 `SongFormModal` / `ScenarioFormModal` 同构。素材特有的两点：
 * 1. **列表行只有 `hasTranscript` 布尔位**（服务端不把转写原文放进列表），而编辑需要原文 ——
 *    所以"编辑前先回读单条"在这里不是优化而是必需：拿列表行回填会让 transcript 变成空串，
 *    保存即把已有转写清掉。
 * 2. `source` 与歌曲共用一套取值域（`public_domain|original|demo_only`）；
 *    `demo_only` 是演示素材，上架前需人工确认版权 —— 选项文案里已点明。
 */
import { computed, ref, watch } from 'vue'
import { NInput, NSelect } from 'naive-ui'

import { consoleApi } from '@/api'
import type { MaterialRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import { describeActionError } from '@/views/content/actionReason'
import ContentFormModal from './ContentFormModal.vue'
import FormField from './FormField.vue'
import { emptyMaterialForm, validateMaterialForm } from './contentFormModel'
import { fillMaterialForm, toMaterialUpsert } from './contentFormPayload'
import type { MaterialForm } from './contentFormTypes'
import {
  INTEREST_TAGS_HINT,
  LEVEL_OPTIONS,
  LICENSE_MAX,
  SOURCE_OPTIONS,
  STATUS_OPTIONS,
  TITLE_MAX,
  URL_MAX,
} from './formMeta'
import { useContentForm } from './useContentForm'

const props = defineProps<{
  /** null = 新建；非 null 只用它的 `id` 与标题（详情一律回读） */
  target: MaterialRow | null
}>()

const show = defineModel<boolean>('show', { required: true })
const emit = defineEmits<{ saved: [] }>()

const form = ref<MaterialForm>(emptyMaterialForm())
const original = ref<MaterialForm | null>(null)
const loading = ref(false)
const loadError = ref<string | null>(null)
const loadErrorCode = ref<number | null>(null)

const { submitting, errors, failure, clearField, run } = useContentForm()

const isEdit = computed(() => props.target !== null)
const title = computed(() =>
  isEdit.value ? `编辑听力素材 · ${props.target?.title ?? ''}` : '新建听力素材',
)
const ready = computed(() => !isEdit.value || original.value !== null)

function editText(key: keyof MaterialForm, value: string): void {
  form.value = { ...form.value, [key]: value }
  clearField(key)
}

function editNumber(key: keyof MaterialForm, value: number | null): void {
  form.value = { ...form.value, [key]: value }
  clearField(key)
}

/**
 * 回读单条。
 *
 * ⚠️ 这里的回读**不只是**为了拿全字段：`replaceLrc` 那类"服务端管、表单没有"的列在素材域不存在，
 * 但 transcript 原文只在单条视图里（`MaterialDetail.transcript`，列表行只有布尔位）——
 * 不回读就等于每次保存都清掉转写，而上架校验与听力练习都依赖它。
 */
async function load(): Promise<void> {
  form.value = emptyMaterialForm()
  original.value = null
  loadError.value = null
  loadErrorCode.value = null
  if (!props.target) return
  loading.value = true
  try {
    const detail = await consoleApi.getMaterial(props.target.id)
    form.value = fillMaterialForm(detail)
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
    validate: () => validateMaterialForm(form.value),
    // 全量提交（理由同 SongFormModal：applyMaterial 无条件覆盖每个字段，且 status 缺省回落 draft）
    submit: () =>
      props.target
        ? consoleApi.updateMaterial(props.target.id, toMaterialUpsert(form.value))
        : consoleApi.createMaterial(toMaterialUpsert(form.value)),
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
      empty-text="正在读取素材详情…（列表行只有 hasTranscript 布尔位，转写原文必须回读）"
      :min-height="120"
    >
      <FormField label="标题" required :error="errors.title" :hint="`服务端上限 ${TITLE_MAX} 字符（@Size）`">
        <n-input :value="form.title" @update:value="editText('title', $event)" />
      </FormField>

      <FormField label="难度 / 等级" required :error="errors.level" hint="1–4（@NotNull @Min(1) @Max(4)）">
        <n-select
          :value="form.level"
          :options="[...LEVEL_OPTIONS]"
          placeholder="请选择"
          @update:value="editNumber('level', $event)"
        />
      </FormField>

      <FormField label="音频地址" required :error="errors.audioUrl" :hint="`上限 ${URL_MAX} 字符（@Size）`">
        <n-input :value="form.audioUrl" placeholder="/api/v1/media/xxx.mp3" @update:value="editText('audioUrl', $event)" />
      </FormField>

      <FormField label="时长（秒）" :error="errors.durationS" hint="留空 = 不设置（发 null，不是 0）">
        <n-input :value="form.durationS" @update:value="editText('durationS', $event)" />
      </FormField>

      <FormField label="转写文本" :error="errors.transcript" hint="听力练习与上架校验都会读它；留空时列表的「转写」列显示缺失">
        <n-input
          :value="form.transcript"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 12 }"
          @update:value="editText('transcript', $event)"
        />
      </FormField>

      <FormField label="兴趣标签" :error="errors.interestTags" :hint="INTEREST_TAGS_HINT">
        <n-input :value="form.interestTags" placeholder="[&quot;news&quot;]" @update:value="editText('interestTags', $event)" />
      </FormField>

      <FormField label="版权来源" :error="errors.source" hint="demo_only = 演示素材，上架前需人工确认版权">
        <n-select
          :value="form.source"
          :options="[...SOURCE_OPTIONS]"
          @update:value="editText('source', $event)"
        />
      </FormField>

      <FormField label="授权说明" :error="errors.license" :hint="`上限 ${LICENSE_MAX} 字符（@Size）`">
        <n-input :value="form.license" @update:value="editText('license', $event)" />
      </FormField>

      <FormField label="状态" :error="errors.status">
        <n-select
          :value="form.status"
          :options="[...STATUS_OPTIONS]"
          @update:value="editText('status', $event)"
        />
      </FormField>
    </AsyncBlock>
  </ContentFormModal>
</template>
