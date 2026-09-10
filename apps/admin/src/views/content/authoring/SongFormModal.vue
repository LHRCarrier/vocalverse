<script setup lang="ts">
/**
 * 歌曲新建 / 编辑弹窗（`POST /content/songs` · `PUT /content/songs/{id}`）。
 *
 * 权威：`console/content/ConsoleContentWriteController` 的 `SongUpsert` record
 * （`@NotBlank @Size(max=128) title`、`@NotNull @Min(1) @Max(4) level`、
 * `@Size(max=512) audioUrl` 等），逐字段对齐，不自行加减。
 *
 * 三个刻意的设计：
 * 1. **编辑必须先回读单条**（`getSong`）：列表行 `SongRowList` 只有 6 个字段，
 *    用它回填会让 `durationS`/`bpm`/`musicalKey`/`lrcUrl`/`coverUrl` 变成空串，
 *    下一次 PUT 就把库里的值清掉了；
 * 2. **只发改动字段**（`songUpsertFromForm`）：服务端 `applySong` 对 null 字段回落默认值
 *    （`status→draft`、`source→public_domain`、`pitchRefStatus→missing`），全量发回会
 *    把已上架的歌曲打回草稿、把已就绪的参考旋律重置；
 * 3. **不提供 `pitchRefStatus` 输入框**：它由 Python 离线任务写（见 `serverFieldErrors.REMOTE_FIELDS`），
 *    手工改只会让跟唱评分用错参考音高。
 *
 * LRC 不在这里编：歌词是**发布前置条件**且行数多，单独一个编辑器（`LrcEditorModal`），
 * 歌曲行上直接有「歌词」入口 —— 藏进本弹窗会让"缺 LRC 导致上架被拦"变成死胡同。
 */
import { computed, ref, watch } from 'vue'
import { NButton, NInput, NSelect } from 'naive-ui'

import { consoleApi } from '@/api'
import type { SongRow } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import PermissionGate from '@/components/common/PermissionGate.vue'
import { describeActionError } from '@/views/content/actionReason'
import ContentFormModal from './ContentFormModal.vue'
import FormField from './FormField.vue'
import { emptySongForm, validateSongForm } from './contentFormModel'
import { fillSongForm, toSongUpsert } from './contentFormPayload'
import type { SongForm } from './contentFormTypes'
import { useContentForm } from './useContentForm'
import {
  LEVEL_OPTIONS,
  MUSICAL_KEY_MAX,
  SOURCE_OPTIONS,
  STATUS_OPTIONS,
  TITLE_MAX,
  URL_MAX,
} from './formMeta'
import LrcEditorModal from './LrcEditorModal.vue'

const props = defineProps<{
  /** null = 新建；非 null 只用它的 `id` 与标题（详情一律回读） */
  target: SongRow | null
}>()

const show = defineModel<boolean>('show', { required: true })
const emit = defineEmits<{ saved: [] }>()

const form = ref<SongForm>(emptySongForm())
/** 回读到的原始表单值：更新时用它算"改了哪些字段" */
const original = ref<SongForm | null>(null)
const loading = ref(false)
const loadError = ref<string | null>(null)
const loadErrorCode = ref<number | null>(null)
const lrcCount = ref<number | null>(null)
const showLrc = ref(false)

const { submitting, errors, failure, clearField, run } = useContentForm()

const isEdit = computed(() => props.target !== null)
const title = computed(() => (isEdit.value ? `编辑歌曲 · ${props.target?.title ?? ''}` : '新建歌曲'))
const ready = computed(() => !isEdit.value || original.value !== null)

/**
 * 改一个字段的值并撤掉它的红字（"用户开始改就清错"，不用等再次提交）。
 *
 * 为什么不用一个泛型 `edit<K>(key, value)`：naive-ui 的 `n-select` 校验事件回调签名是
 * `(value: string & number & … ) => void`（各取值域的**交叉**类型），泛型会推导失败；
 * 分成两个按类型收窄的函数，既满足类型又能把运行时值窄回表单字段的真实类型
 * （下拉的数值字段只可能吐 number，文本框只可能吐 string）。
 */
function editText(key: keyof SongForm, value: string): void {
  form.value = { ...form.value, [key]: value }
  clearField(key)
}

function editNumber(key: keyof SongForm, value: number | null): void {
  form.value = { ...form.value, [key]: value }
  clearField(key)
}

/**
 * 回读单条 + LRC 行数。
 *
 * LRC 行数只是**提示**（发布前置条件之一，docs/50 §6.1）：拉不到不算失败，
 * 故单独 catch 并把 `lrcCount` 置 null（页面显示「未知」，不假装是 0 —— 0 会被读成"确认没有歌词"）。
 */
async function load(): Promise<void> {
  form.value = emptySongForm()
  original.value = null
  lrcCount.value = null
  loadError.value = null
  loadErrorCode.value = null
  if (!props.target) return
  loading.value = true
  try {
    const detail = await consoleApi.getSong(props.target.id)
    form.value = fillSongForm(detail)
    original.value = { ...form.value }
  } catch (err) {
    const described = describeActionError(err)
    loadError.value = described.message
    loadErrorCode.value = described.code
  } finally {
    loading.value = false
  }
  try {
    lrcCount.value = (await consoleApi.getSongLrc(props.target.id)).length
  } catch {
    lrcCount.value = null
  }
}

watch(show, (open) => {
  if (open) void load()
})

async function onSubmit(): Promise<void> {
  const ok = await run({
    validate: () => validateSongForm(form.value),
    // ⚠️ 发**全量** SongUpsert，不发"只改动字段"的补丁。
    //
    // 原因（2026-09-10 实测）：服务端 `ConsoleContentWriteController.applySong` **无条件覆盖每个字段**
    // （`e.setTitle(b.title())` … 没有 null 跳过）。于是"只发改动字段"的补丁会：
    //   ① 因 `@NotBlank title` 直接 46007；② 即便绕过校验，也会把未提交的字段写成 null；
    //   ③ 最阴的一条：`pitchRefStatus` 不在表单里（它由 Python 离线任务写），发补丁会让它被重置成
    //      `"missing"` —— 上架前置校验（要求 ready）与跟唱评分的参考音高会一起坏掉。
    // 本表单在编辑前**已先回读单条**（load()），所以手上的值就是库里的值，发全量是安全的。
    submit: () =>
      props.target
        ? consoleApi.updateSong(props.target.id, toSongUpsert(form.value))
        : consoleApi.createSong(toSongUpsert(form.value)),
    onSuccess: () => {
      show.value = false
      emit('saved')
    },
  })
  if (ok && props.target) await load()
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
      empty-text="正在读取歌曲详情…（编辑前先回读：列表行只有 6 个字段，直接回填会让未展示的字段变成空值）"
      :min-height="120"
    >
      <FormField label="标题" required :error="errors.title" :hint="`服务端上限 ${TITLE_MAX} 字符（@Size）`">
        <n-input
          :value="form.title"
          placeholder="如 Twinkle Twinkle Little Star"
          @update:value="editText('title', $event)"
        />
      </FormField>

      <FormField label="歌手" :error="errors.artist">
        <n-input :value="form.artist" placeholder="可留空" @update:value="editText('artist', $event)" />
      </FormField>

      <div class="flex gap-3">
        <div class="flex-1">
          <FormField label="难度 / 等级" required :error="errors.level" hint="服务端 @Min(1) @Max(4)">
            <n-select
              :value="form.level"
              :options="[...LEVEL_OPTIONS]"
              placeholder="请选择"
              @update:value="editNumber('level', $event)"
            />
          </FormField>
        </div>
        <div class="flex-1">
          <FormField label="时长（秒）" :error="errors.durationS" hint="可留空；`@Min(0)`">
            <n-input
              :value="form.durationS"
              placeholder="如 215"
              @update:value="editText('durationS', $event)"
            />
          </FormField>
        </div>
        <div class="flex-1">
          <FormField label="BPM" :error="errors.bpm" hint="可留空；支持小数（BigDecimal）">
            <n-input :value="form.bpm" placeholder="如 120.5" @update:value="editText('bpm', $event)" />
          </FormField>
        </div>
      </div>

      <FormField
        label="调性"
        :error="errors.musicalKey"
        :hint="`如 C / Am；服务端上限 ${MUSICAL_KEY_MAX} 字符（@Size(max=8)）`"
      >
        <n-input
          :value="form.musicalKey"
          placeholder="可留空"
          @update:value="editText('musicalKey', $event)"
        />
      </FormField>

      <FormField
        label="音频地址"
        required
        :error="errors.audioUrl"
        :hint="`@NotBlank @Size(max=${URL_MAX})；上架校验还会拦空串（PublishService.validateSong）`"
      >
        <n-input
          :value="form.audioUrl"
          placeholder="如 /media/songs/twinkle.mp3"
          @update:value="editText('audioUrl', $event)"
        />
      </FormField>

      <FormField label="LRC 文件地址" :error="errors.lrcUrl" :hint="`@Size(max=${URL_MAX})，可留空`">
        <n-input :value="form.lrcUrl" placeholder="可选" @update:value="editText('lrcUrl', $event)" />
      </FormField>

      <FormField label="封面地址" :error="errors.coverUrl" :hint="`@Size(max=${URL_MAX})，可留空`">
        <n-input :value="form.coverUrl" placeholder="可选" @update:value="editText('coverUrl', $event)" />
      </FormField>

      <FormField
        label="兴趣标签"
        :error="errors.interestTags"
        hint="JSON 数组文本，如 [&quot;pop&quot;,&quot;kids&quot;]；留空 = 不设置（服务端存 &quot;[]&quot;）"
      >
        <n-input
          :value="form.interestTags"
          placeholder="[&quot;pop&quot;]"
          @update:value="editText('interestTags', $event)"
        />
      </FormField>

      <FormField
        label="版权来源"
        :error="errors.source"
        hint="@Pattern(public_domain|original|demo_only)；上架前需确认 demo_only 素材的授权"
      >
        <n-select
          :value="form.source"
          :options="[...SOURCE_OPTIONS]"
          @update:value="editText('source', $event)"
        />
      </FormField>

      <FormField
        label="状态"
        :error="errors.status"
        hint="这里只改元数据；「上架」是列表页的独立动作，会跑前置校验并按逐字段原因报错（docs/50 §6.1）"
      >
        <n-select
          :value="form.status"
          :options="[...STATUS_OPTIONS]"
          @update:value="editText('status', $event)"
        />
      </FormField>

      <FormField
        v-if="isEdit"
        label="LRC 歌词"
        hint="歌曲上架的前置校验要求 LRC 行数 ≥ 1，且音高参考旋律须为 ready（docs/50 §6.1）"
      >
        <div class="flex items-center gap-2">
          <span class="c-weak text-12px">
            {{ lrcCount === null ? '当前行数未知（读取失败）' : `当前 ${lrcCount} 行` }}
          </span>
          <PermissionGate code="content:song:write">
            <n-button size="tiny" @click="showLrc = true">打开歌词编辑器</n-button>
          </PermissionGate>
        </div>
      </FormField>
    </AsyncBlock>
  </ContentFormModal>

  <!-- LRC 编辑器在歌曲弹窗之上再开一层：它不是"保存歌曲"的一部分（PUT 就立即生效），
       因此在歌词里保存不会顺带提交本表单的未保存字段 -->
  <LrcEditorModal v-if="target" v-model:show="showLrc" :song-id="target.id" :song-title="target.title" />
</template>
