<script setup lang="ts">
/**
 * 场景新建 / 编辑弹窗（`POST|PUT /content/scenarios`）。
 *
 * 与 `SongFormModal` 同构（外壳 / 本地预检 / 服务端错误归位 / **编辑前先回读单条**），
 * 差异只有字段集与两处场景特有的说明：
 * 1. `targetCorpus`（目标语料）是**上架前置条件**：`PublishService.validateScenario` 要求
 *    ≥ 3 条语言点，且按 `English phrase|中文释义` 逐行解析（与 Python `corpus.py` 同口径）——
 *    所以它用多行输入，并把权威格式写在提示里，而不是让运营提交后吃 46011 才知道格式不对。
 * 2. `sceneType` 是**封闭取值域**（`@Pattern`），不是自由文本；写成输入框会让五个合法值
 *    变成"猜"。
 */
import { computed, ref, watch } from 'vue'
import { NInput, NSelect } from 'naive-ui'

import { consoleApi } from '@/api'
import type { ScenarioRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import { describeActionError } from '@/views/content/actionReason'
import ContentFormModal from './ContentFormModal.vue'
import FormField from './FormField.vue'
import { emptyScenarioForm, validateScenarioForm } from './contentFormModel'
import { fillScenarioForm, toScenarioUpsert } from './contentFormPayload'
import type { ScenarioForm } from './contentFormTypes'
import {
  INTEREST_TAGS_HINT,
  LEVEL_OPTIONS,
  SCENE_TYPE_OPTIONS,
  STATUS_OPTIONS,
  TARGET_CORPUS_HINT,
  URL_MAX,
} from './formMeta'
import { useContentForm } from './useContentForm'

const props = defineProps<{
  /** null = 新建；非 null 只用它的 `id` 与标题（详情一律回读） */
  target: ScenarioRow | null
}>()

const show = defineModel<boolean>('show', { required: true })
const emit = defineEmits<{ saved: [] }>()

const form = ref<ScenarioForm>(emptyScenarioForm())
/** 回读到的原始表单值（当前提交发全量，故只用于判断"是否可以开始编辑"） */
const original = ref<ScenarioForm | null>(null)
const loading = ref(false)
const loadError = ref<string | null>(null)
const loadErrorCode = ref<number | null>(null)

const { submitting, errors, failure, clearField, run } = useContentForm()

const isEdit = computed(() => props.target !== null)
const title = computed(() => (isEdit.value ? `编辑场景 · ${props.target?.title ?? ''}` : '新建场景'))
const ready = computed(() => !isEdit.value || original.value !== null)

/** 改一个字段并撤掉它的红字（"用户开始改就清错"，不用等再次提交） */
function editText(key: keyof ScenarioForm, value: string): void {
  form.value = { ...form.value, [key]: value }
  clearField(key)
}

/** 数字下拉单独一个函数：`n-select` 的取值域是 `string & number`，泛型推导会失败 */
function editNumber(key: keyof ScenarioForm, value: number | null): void {
  form.value = { ...form.value, [key]: value }
  clearField(key)
}

/** 回读单条：列表行只投影 4 个字段（title/sceneType/difficulty/corpusItemCount），不能用来回填 */
async function load(): Promise<void> {
  form.value = emptyScenarioForm()
  original.value = null
  loadError.value = null
  loadErrorCode.value = null
  if (!props.target) return
  loading.value = true
  try {
    const detail = await consoleApi.getScenario(props.target.id)
    form.value = fillScenarioForm(detail)
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
    validate: () => validateScenarioForm(form.value),
    // 与歌曲同理发**全量**：服务端 `applyScenario` 对每个字段无条件覆盖
    // （`e.setEstimatedTurns(b.estimatedTurns())` … 没有 null 跳过，且 status 缺省回落 draft），
    // 发"只改动字段"的补丁会把未提交的字段写成 null。本弹窗编辑前已回读单条，手里的值即库里的值。
    submit: () =>
      props.target
        ? consoleApi.updateScenario(props.target.id, toScenarioUpsert(form.value))
        : consoleApi.createScenario(toScenarioUpsert(form.value)),
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
      empty-text="正在读取场景详情…（编辑前先回读：列表行只有 4 个字段）"
      :min-height="120"
    >
      <FormField label="场景标题" required :error="errors.title">
        <n-input :value="form.title" placeholder="如 At the café" @update:value="editText('title', $event)" />
      </FormField>

      <FormField label="场景类型" required :error="errors.sceneType" hint="封闭取值域（服务端 @Pattern），不在列表里的值会被拒">
        <n-select
          :value="form.sceneType"
          :options="[...SCENE_TYPE_OPTIONS]"
          placeholder="请选择"
          @update:value="editText('sceneType', $event)"
        />
      </FormField>

      <FormField label="难度" required :error="errors.difficulty" hint="1–4（@Min(1) @Max(4)）">
        <n-select
          :value="form.difficulty"
          :options="[...LEVEL_OPTIONS]"
          placeholder="请选择"
          @update:value="editNumber('difficulty', $event)"
        />
      </FormField>

      <FormField label="系统提示词" required :error="errors.systemPrompt" hint="喂给 LLM 的角色设定（不进用户可见文案）">
        <n-input
          :value="form.systemPrompt"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          @update:value="editText('systemPrompt', $event)"
        />
      </FormField>

      <FormField label="开场白" required :error="errors.openingLine" hint="上架前置条件之一（validateScenario 要求非空）">
        <n-input :value="form.openingLine" @update:value="editText('openingLine', $event)" />
      </FormField>

      <FormField label="目标语料" :error="errors.targetCorpus" :hint="TARGET_CORPUS_HINT">
        <n-input
          :value="form.targetCorpus"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 12 }"
          placeholder="Where is the gate?|登机口在哪里？&#10;A cup of coffee, please.|请来一杯咖啡。"
          @update:value="editText('targetCorpus', $event)"
        />
      </FormField>

      <FormField label="场景描述" :error="errors.description" :hint="`展示给用户的场景说明，上限 ${URL_MAX} 字符`">
        <n-input :value="form.description" @update:value="editText('description', $event)" />
      </FormField>

      <FormField label="兴趣标签" :error="errors.interestTags" :hint="INTEREST_TAGS_HINT">
        <n-input :value="form.interestTags" placeholder="[&quot;travel&quot;]" @update:value="editText('interestTags', $event)" />
      </FormField>

      <FormField label="提示词版本" :error="errors.promptVersion" hint="改系统提示词时 +1，便于对照历史效果（@Min(1)）">
        <n-input :value="form.promptVersion" @update:value="editText('promptVersion', $event)" />
      </FormField>

      <FormField label="预计轮次" :error="errors.estimatedTurns">
        <n-input :value="form.estimatedTurns" @update:value="editText('estimatedTurns', $event)" />
      </FormField>

      <FormField label="预计时长（分钟）" :error="errors.estimatedMinutes">
        <n-input :value="form.estimatedMinutes" @update:value="editText('estimatedMinutes', $event)" />
      </FormField>

      <FormField label="状态" :error="errors.status" hint="上架另有前置校验（语料 ≥3 条），列表页的「语言点」列就是它的可视化预检">
        <n-select
          :value="form.status"
          :options="[...STATUS_OPTIONS]"
          @update:value="editText('status', $event)"
        />
      </FormField>
    </AsyncBlock>
  </ContentFormModal>
</template>
