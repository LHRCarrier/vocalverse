<script setup lang="ts">
/**
 * LRC 歌词编辑器（整首重写：`PUT /content/songs/{id}/lrc`）。
 *
 * 为什么不塞进 `SongFormModal` 的一个字段里：歌词是**发布前置条件**（`PublishService.validateSong`
 * 要求 lrc 行数 ≥ 1，docs/50 §6.1），一条都不能少；而它是**变长结构**（几十行 × 3 列），
 * 挤进歌曲表单会让"改歌手名"和"改 40 行歌词"变成同一个提交动作 —— 后者失败时前者的修改也一起丢。
 * 所以歌词单独一个编辑器、单独一次提交（歌曲行上直接有入口，见 `SongsView`）。
 *
 * ## 三个必须在界面上说清楚的服务端事实（不是前端自己加的规矩）
 *
 * 1. **保存歌词会让已就绪的参考旋律失效**：`ConsoleContentWriteController.replaceLrc` 在写完行之后
 *    会把 `songs.pitch_ref_status` 从 `ready` 置回 `missing`（歌词换了，旧旋律就对不上了），
 *    于是这首歌会**暂时无法上架**，直到离线音高提取重跑完。运营不知道这条的话，会以为"改个错别字
 *    把歌改坏了" —— 所以这里常驻提示，并且只在确实会发生时提示（见 `pitchNotice`）。
 * 2. **顺序按 offsetMs 重排**：服务端按**数组下标**写 `seq`，而逐句跟唱评分依赖 `seq` 顺序；
 *    提交前由 `toLrcUpsert` 升序排序，所以运营乱序录入不会把时间轴搞错（但界面仍按录入顺序显示，
 *    避免"我明明放在第 2 行，它跳到第 7 行"的困惑）。
 * 3. **endOffsetMs 留空 = 与起始同值**（零时长行），不是"没有结束时间"：该列 `NOT NULL`，
 *    发 null 会直接报错（`l.setEndOffsetMs(null)`）。提示写在列头上。
 */
import { computed, ref, watch } from 'vue'
import { NButton, NInput } from 'naive-ui'
import IconPlus from '~icons/tabler/plus'
import IconTrash from '~icons/tabler/trash'

import { consoleApi } from '@/api'
import AsyncBlock from '@/components/common/AsyncBlock.vue'
import { describeActionError } from '@/views/content/actionReason'
import ContentFormModal from './ContentFormModal.vue'
import { toLrcFormRows, toLrcUpsert } from './contentFormPayload'
import { validateLrcRows } from './contentFormModel'
import type { FormErrors, LrcFormRow } from './contentFormTypes'
import { useContentForm } from './useContentForm'

const props = defineProps<{
  songId: number
  songTitle: string
  /** 当前歌曲的参考旋律状态：`ready` 时保存歌词会让它失效，界面必须预告（见文件头第 1 条） */
  pitchRefStatus?: string | null
}>()

const show = defineModel<boolean>('show', { required: true })
const emit = defineEmits<{ saved: [] }>()

const rows = ref<LrcFormRow[]>([])
/** 逐行错误（与 `rows` 同下标）；整表错误走 `errors.form`（useContentForm 的形状） */
const rowErrors = ref<FormErrors[]>([])
const loading = ref(false)
const loadError = ref<string | null>(null)
const loadErrorCode = ref<number | null>(null)

const { submitting, errors, failure, clearField, run } = useContentForm()

/** 会失效的参考旋律：只有 `ready` 才值得预告（`missing` 本来就是没就绪，说了反而噪音） */
const pitchNotice = computed(() =>
  props.pitchRefStatus === 'ready'
    ? '保存后这首歌的参考旋律会被置为「未就绪」（服务端 replaceLrc 的行为：歌词变了，旧旋律就对不上），上架会暂时被拦，需等离线提取重跑。'
    : null,
)

async function load(): Promise<void> {
  rows.value = []
  rowErrors.value = []
  loadError.value = null
  loadErrorCode.value = null
  loading.value = true
  try {
    rows.value = toLrcFormRows(await consoleApi.getSongLrc(props.songId))
    rowErrors.value = rows.value.map(() => ({}))
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

function editRow(index: number, key: keyof LrcFormRow, value: string): void {
  const next = [...rows.value]
  next[index] = { ...next[index], [key]: value }
  rows.value = next
  const rowError = rowErrors.value[index]
  if (rowError && key in rowError) {
    const cleaned = { ...rowError }
    delete cleaned[key]
    const all = [...rowErrors.value]
    all[index] = cleaned
    rowErrors.value = all
  }
  // 行级错误清掉之后，整表那句"有歌词行未填完整"也不再成立
  if (errors.value.form) clearField('form')
}

function addRow(): void {
  rows.value = [...rows.value, { offsetMs: '', endOffsetMs: '', lineText: '' }]
  rowErrors.value = [...rowErrors.value, {}]
}

function removeRow(index: number): void {
  rows.value = rows.value.filter((_row, i) => i !== index)
  rowErrors.value = rowErrors.value.filter((_row, i) => i !== index)
}

async function onSubmit(): Promise<void> {
  await run({
    // `validateLrcRows` 同时给出逐行错误与整表错误：逐行的那份在这里落到 `rowErrors`
    // （`useContentForm` 只认扁平的表单错误表，行级错误由本组件自己呈现）。
    validate: () => {
      const { errors: formErrors, rowErrors: perRow } = validateLrcRows(rows.value)
      rowErrors.value = perRow
      return formErrors
    },
    submit: () => consoleApi.replaceSongLrc(props.songId, toLrcUpsert(rows.value)),
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
    :title="`歌词编辑 · ${songTitle}`"
    width-class="w-200"
    :submitting="submitting"
    :failure="failure"
    :has-field-errors="Object.keys(errors).length > 0"
    submit-text="整首保存"
    @submit="onSubmit"
  >
    <p v-if="pitchNotice" class="c-lrc-notice text-12px mb-3" role="status">{{ pitchNotice }}</p>

    <AsyncBlock
      :loading="loading"
      :error="loadError"
      :error-code="loadErrorCode"
      :empty="rows.length === 0 && !loading && !loadError"
      empty-text="这首歌还没有歌词行。上架要求至少 1 行（docs/50 §6.1），请先添加。"
      :min-height="120"
    >
      <div class="c-lrc-head text-12px">
        <span>起始毫秒</span>
        <span>结束毫秒（留空 = 与起始相同）</span>
        <span>歌词文本</span>
        <span />
      </div>

      <div v-for="(row, index) in rows" :key="index" class="c-lrc-row">
        <div>
          <n-input
            :value="row.offsetMs"
            placeholder="0"
            @update:value="editRow(index, 'offsetMs', $event)"
          />
          <div v-if="rowErrors[index]?.offsetMs" class="c-lrc-error text-12px" role="alert">
            {{ rowErrors[index]?.offsetMs }}
          </div>
        </div>
        <div>
          <n-input
            :value="row.endOffsetMs"
            placeholder="留空"
            @update:value="editRow(index, 'endOffsetMs', $event)"
          />
          <div v-if="rowErrors[index]?.endOffsetMs" class="c-lrc-error text-12px" role="alert">
            {{ rowErrors[index]?.endOffsetMs }}
          </div>
        </div>
        <div>
          <n-input
            :value="row.lineText"
            placeholder="这一行唱什么"
            @update:value="editRow(index, 'lineText', $event)"
          />
          <div v-if="rowErrors[index]?.lineText" class="c-lrc-error text-12px" role="alert">
            {{ rowErrors[index]?.lineText }}
          </div>
        </div>
        <n-button quaternary size="small" title="删除这一行" @click="removeRow(index)">
          <IconTrash width="16" height="16" aria-hidden="true" />
        </n-button>
      </div>

      <div class="flex items-center gap-2 mt-3">
        <n-button size="small" @click="addRow">
          <template #icon><IconPlus width="16" height="16" aria-hidden="true" /></template>
          添加一行
        </n-button>
        <span class="c-weak text-12px">
          共 {{ rows.length }} 行 · 提交时按起始毫秒升序重排（跟唱评分依赖 seq 顺序）
        </span>
      </div>

      <p v-if="errors.form" class="c-lrc-error text-12px mt-2" role="alert">{{ errors.form }}</p>
      <p class="c-weak text-12px mt-2">
        服务端是「整首替换」：本次提交会删掉旧的全部歌词行再插入这里的行（不是增量修改）。
      </p>
    </AsyncBlock>
  </ContentFormModal>
</template>

<style scoped>
.c-lrc-notice {
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--c-warn-soft, rgba(214, 158, 46, 0.12));
  color: var(--c-warn);
}
.c-lrc-head,
.c-lrc-row {
  display: grid;
  grid-template-columns: 120px 200px 1fr 40px;
  gap: 8px;
  align-items: start;
}
.c-lrc-head {
  color: var(--c-text-2);
  padding-bottom: 4px;
}
.c-lrc-row {
  margin-bottom: 8px;
}
.c-lrc-error {
  color: var(--c-danger);
}
</style>
