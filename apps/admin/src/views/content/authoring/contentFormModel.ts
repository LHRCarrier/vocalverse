/**
 * 内容写入表单的**空值默认、标量解析与本地预检**（纯函数）。
 *
 * 这一层是"前端自己的规矩"：服务端能报错的地方这里提前报，好让运营在提交前看到
 * 字段级红字；每一条校验都必须是服务端约束的**子集**（宁可漏报也不许误报 ——
 * 误报会让运营改一个其实没问题的字段）。口径见 `contentFormTypes.ts` 文件头。
 *
 * 解析函数（`parseWhole` / `parseDecimal` / `trimmedOrNull`）在这里而不是 payload 层，
 * 是因为**预检与转换必须用同一个解析器**：两份实现必然出现"预检说合法、转换出来是 null"。
 */

import { fieldMeta } from './formMeta'
import type { FormFieldKey } from './formMeta'
import type {
  FormErrors,
  LrcFormRow,
  MaterialForm,
  QuestionForm,
  ScenarioForm,
  SongForm,
} from './contentFormTypes'

// ── 空值默认 ──────────────────────────────────────────────────────────────

/** 未选的数字下拉用 `null`（naive-ui 的 `n-select` 空值是 null，不是 0 —— 0 会被当成用户填了 0 级） */
export function emptySongForm(): SongForm {
  return {
    title: '',
    artist: '',
    level: null,
    durationS: '',
    bpm: '',
    musicalKey: '',
    audioUrl: '',
    lrcUrl: '',
    coverUrl: '',
    interestTags: '',
    source: 'public_domain',
    status: 'draft',
  }
}

export function emptyScenarioForm(): ScenarioForm {
  return {
    title: '',
    sceneType: null,
    difficulty: null,
    description: '',
    systemPrompt: '',
    openingLine: '',
    targetCorpus: '',
    interestTags: '',
    promptVersion: '1',
    estimatedTurns: '',
    estimatedMinutes: '',
    status: 'draft',
  }
}

export function emptyMaterialForm(): MaterialForm {
  return {
    title: '',
    level: null,
    audioUrl: '',
    durationS: '',
    transcript: '',
    interestTags: '',
    source: 'public_domain',
    license: '',
    status: 'draft',
  }
}

export function emptyQuestionForm(): QuestionForm {
  return {
    examRevision: '1',
    itemIndex: '',
    kind: 'read',
    prompt: '',
    referenceAnswer: '',
    // 题库默认 published（`createQuestion`：`status == null ? "published"`；题库没有"半成品题目"）
    status: 'published',
  }
}

// ── 标量解析（预检与转换共用，见文件头） ──────────────────────────────────

/** 空串 / 纯空白视为"未填"（服务端 `@NotBlank` 同义） */
export function isBlank(value: string | null | undefined): boolean {
  return value === null || value === undefined || value.trim() === ''
}

/** trim 后的值；空 → null（`contentFormTypes.ts` 文件头第 2 条） */
export function trimmedOrNull(value: string): string | null {
  const t = value.trim()
  return t === '' ? null : t
}

/** 整数文本 → 数字；空 → undefined（"没填"，与填了非法值的 null 区分开） */
export function parseWhole(value: string): number | undefined | null {
  const t = value.trim()
  if (t === '') return undefined
  return /^\d+$/.test(t) ? Number(t) : null
}

/** 十进制文本 → 数字（允许 `120.5` 与本地化的 `120,5`）；空 → undefined */
export function parseDecimal(value: string): number | undefined | null {
  const t = value.trim().replace(',', '.')
  if (t === '') return undefined
  return /^\d+(\.\d+)?$/.test(t) ? Number(t) : null
}

// ── 预检 ──────────────────────────────────────────────────────────────────

/**
 * 按元数据校验一个文本/数字/枚举字段。返回提示语或 null（通过）。
 *
 * 为什么不用 naive-ui 的 `n-form` rules：本项目四个弹窗的字段形状差异很大
 * （含可变行数与 Java 属性名不同名的字段），rules 的 key 是**表单 key**，
 * 而服务端报错给的是 **Java 属性名** —— 两套 key 混在一起正是"错误归不到字段"的成因。
 * 这里所有校验与归位都只认表单 key，映射在 `serverFieldErrors.ts` 的 `fieldKeyOfJava` 一处完成。
 */
export function checkField(key: FormFieldKey, value: unknown): string | null {
  const meta = fieldMeta(key)
  if (!meta) return null
  // 数字下拉 / 枚举：null 一律按必填处理（`@NotNull`），否则按取值域
  if (meta.kind === 'enum' || meta.kind === 'int') {
    if (value === null || value === undefined) return meta.requiredHint ?? null
  }
  if (meta.kind === 'text' || meta.kind === 'lines') {
    const text = typeof value === 'string' ? value : ''
    if (meta.requiredHint && isBlank(text)) return meta.requiredHint
    if (meta.maxLength !== undefined && text.length > meta.maxLength) {
      return `长度上限 ${meta.maxLength} 个字符（服务端 @Size）`
    }
    return null
  }
  if (meta.kind === 'int' || meta.kind === 'decimal') {
    if (typeof value !== 'string') return null
    if (meta.requiredHint && isBlank(value)) return meta.requiredHint
    const parsed = meta.kind === 'int' ? parseWhole(value) : parseDecimal(value)
    if (parsed === undefined) return null
    if (parsed === null) return meta.kind === 'int' ? '请填整数' : '请填数字'
    if (meta.min !== undefined && parsed < meta.min) return `不得小于 ${meta.min}`
    if (meta.max !== undefined && parsed > meta.max) return `不得大于 ${meta.max}`
    return null
  }
  if (meta.kind === 'json') {
    const text = typeof value === 'string' ? value.trim() : ''
    if (text === '') return null
    try {
      const parsed: unknown = JSON.parse(text)
      if (!Array.isArray(parsed)) return '必须是 JSON 数组（如 ["pop"]）'
      return parsed.every((v) => typeof v === 'string') ? null : '数组元素必须是字符串'
    } catch {
      return '不是合法 JSON'
    }
  }
  return null
}

/** 遍历字段元数据收集错误：只校验**该表单实际暴露**的字段（未暴露的不产生假错误） */
function collect(form: Record<string, unknown>, keys: FormFieldKey[]): FormErrors {
  const errors: FormErrors = {}
  for (const key of keys) {
    const message = checkField(key, form[key])
    if (message) errors[key] = message
  }
  return errors
}

/** 歌曲 / 场景 / 听力素材共用的字段集合（避免每个表单各写一遍 key 列表） */
const COMMON_TEXT: FormFieldKey[] = ['title', 'interestTags']

export function validateSongForm(form: SongForm): FormErrors {
  const errors = collect(
    { ...form },
    [...COMMON_TEXT, 'artist', 'level', 'durationS', 'bpm', 'musicalKey', 'audioUrl', 'lrcUrl', 'coverUrl', 'source'],
  )
  return errors
}

export function validateScenarioForm(form: ScenarioForm): FormErrors {
  return collect(
    { ...form },
    [
      ...COMMON_TEXT,
      'sceneType',
      'difficulty',
      'description',
      'systemPrompt',
      'openingLine',
      'targetCorpus',
      'promptVersion',
      'estimatedTurns',
      'estimatedMinutes',
      'status',
    ],
  )
}

export function validateMaterialForm(form: MaterialForm): FormErrors {
  return collect(
    { ...form },
    [...COMMON_TEXT, 'level', 'audioUrl', 'durationS', 'transcript', 'source', 'license', 'status'],
  )
}

export function validateQuestionForm(form: QuestionForm): FormErrors {
  return collect(
    { ...form },
    ['examRevision', 'itemIndex', 'kind', 'prompt', 'referenceAnswer', 'status'],
  )
}

/**
 * LRC 行预检。
 *
 * 三条都不是"前端自己加的规矩"，逐条对着 Java 写：
 * - `offsetMs` 是 `@NotNull @Min(0)`，缺失时服务端 500（不是 4xx）—— 因为 `@Valid` 失败后落到
 *   `GlobalExceptionHandler` 的兜底分支才被识别，而 LRC 数组元素里的 null 会先触发 NPE 路径；
 * - `lineText` 是 `@NotBlank`；
 * - `endOffsetMs` 是 `@Min(0)` **可空**：留空时提交 start（同值 = 零时长行），
 *   而不是发 null —— `replaceLrc` 里 `l.setEndOffsetMs(null)` 会让 `NOT NULL` 列报错。
 */
export function validateLrcRows(rows: LrcFormRow[]): { errors: FormErrors; rowErrors: FormErrors[] } {
  const rowErrors: FormErrors[] = rows.map((row) => {
    const rowError: FormErrors = {}
    const offset = parseWhole(row.offsetMs)
    if (offset === undefined || offset === null) rowError.offsetMs = '起始毫秒必填（非负整数）'
    if (isBlank(row.lineText)) rowError.lineText = '歌词行文本必填'
    const end = parseWhole(row.endOffsetMs)
    if (end === null) rowError.endOffsetMs = '结束毫秒必须是非负整数（留空 = 与起始相同）'
    return rowError
  })
  const errors: FormErrors = {}
  if (rows.length === 0) {
    errors.form = '至少 1 行歌词：歌曲上架的前置校验要求 lrc 行数 ≥ 1（docs/50 §6.1）'
  }
  if (rows.some((_row, index) => Object.keys(rowErrors[index]).length > 0)) {
    errors.form = '有歌词行未填完整，请修好标红的行再提交'
  }
  return { errors, rowErrors }
}
