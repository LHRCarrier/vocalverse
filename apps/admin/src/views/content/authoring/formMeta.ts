/**
 * 内容写入表单的**元数据**：下拉选项 + Java 字段名 → 表单 field 的映射表。
 *
 * 为什么单独一个文件（而不是散在四个弹窗里）：这些取值域**全部来自后端注解**，
 * 是"改了以后前端会静默发非法值、直到运营点了保存才吃 422"的那类字面量。
 * 集中一处才能逐个标注权威来源（其余文件只引用 `SCENE_TYPES` 这类常量，不重复字面量）。
 */

import type { NButton } from 'naive-ui'

/** 按钮类型（模板里 `ref<NButton>` 用；由本文件再导出，免得各弹窗各引一次 naive-ui 类型） */
export type FormButtonRef = InstanceType<typeof NButton>

/** 表单字段类型（决定校验分支；不是 UI 类型——UI 由各弹窗自己画） */
export type FormFieldKind = 'text' | 'int' | 'decimal' | 'enum' | 'lines' | 'json' | 'list'

export interface FormFieldMeta {
  /** 表单内的 key（与 payload 映射表里的键一致；LRC 行是 `lines`） */
  field: string
  /** 中文名（错误提示里用"音频地址"而不是"audioUrl"） */
  label: string
  kind: FormFieldKind
  /** 服务端要求必填时的提示语（与 Java 注解同义，不是"随手加的前端规则"） */
  requiredHint?: string
  /** 长度上限（`@Size(max=…)`） */
  maxLength?: number
  /** 整数取值域（`@Min`/`@Max`，如 level 1–4） */
  min?: number
  max?: number
  /** 枚举取值域（`@Pattern(regexp=…)` 展开） */
  options?: readonly string[]
  /**
   * 服务端**非 Bean Validation** 报错文案里出现这些词就归到本字段。
   * 只用于 46007 一类没有字段名的业务拒绝（42201 走 `parseJavaFieldError` 的精确解析）。
   */
  keywords?: readonly string[]
}

// ── 下拉选项（逐条对齐 Java 注解的取值域） ────────────────────────────────

/** 内容状态（`PublishService.STATUS_*`；题库无 draft，故另有一份两态选项） */
export const STATUS_OPTIONS = [
  { label: '草稿', value: 'draft' },
  { label: '已上架', value: 'published' },
  { label: '已下架', value: 'archived' },
] as const

/** 题库状态（`QuestionUpsert.status` 的 `@Pattern` 只有 published|archived） */
export const QUESTION_STATUS_OPTIONS = [
  { label: '已启用', value: 'published' },
  { label: '已归档', value: 'archived' },
] as const

/**
 * 版权来源（`SongUpsert.source` / `MaterialUpsert.source` 的 `@Pattern`）。
 * `demo_only` 是演示素材，上架前需人工确认版权——文案里点明，避免误选。
 */
export const SOURCE_OPTIONS = [
  { label: '公版（public_domain）', value: 'public_domain' },
  { label: '原创（original）', value: 'original' },
  { label: '仅演示（demo_only）', value: 'demo_only' },
] as const

/** 场景类型（`ScenarioUpsert.sceneType` 的 `@Pattern`）：**封闭**取值域，不是自由文本 */
export const SCENE_TYPE_OPTIONS = [
  { label: '咖啡馆（cafe）', value: 'cafe' },
  { label: '机场（airport）', value: 'airport' },
  { label: '面试（interview）', value: 'interview' },
  { label: '图书馆（library）', value: 'library' },
  { label: '其它（other）', value: 'other' },
] as const

/** 题目类型（`QuestionUpsert.kind`）：read=朗读题（跟读评分）、qa=问答题 */
export const QUESTION_KIND_OPTIONS = [
  { label: '朗读题（read）', value: 'read' },
  { label: '问答题（qa）', value: 'qa' },
] as const

/** 难度 / 等级 1–4（`@Min(1) @Max(4)`，四个内容域同一套） */
export const LEVEL_OPTIONS = [
  { label: '1 · 入门', value: 1 },
  { label: '2 · 初级', value: 2 },
  { label: '3 · 中级', value: 3 },
  { label: '4 · 高级', value: 4 },
] as const

/**
 * 目标语料的**权威格式**（`PublishService.countCorpusItems` + `app/practice/corpus.py` 同口径）：
 * 逐行一条，`English phrase|中文释义`，只统计含 `|` 且 `|` 前有实际短语的行。
 * 上架要求 ≥3 条 —— 这条格式说明就是那次 46011 的可操作版本。
 */
export const TARGET_CORPUS_HINT =
  '每行一条语言点，格式 `English phrase|中文释义`（与 Python 解析口径一致，PublishService.countCorpusItems）。上架要求 ≥ 3 条。'

/** 兴趣标签列的事实格式：JSON 数组**文本**（Java `String interestTags`；空值服务端回落 `"[]"`） */
export const INTEREST_TAGS_HINT =
  'JSON 数组文本，如 ["pop","jazz"]；留空表示不设置（服务端存 "[]"，不是 NULL）。'

/** `title` 等文本字段的长度上限来源：`SongUpsert.title` 等 `@Size(max=128)` */
export const TITLE_MAX = 128
/** `audioUrl` / `lrcUrl` / `coverUrl` / `description` 的 `@Size(max=512)` */
export const URL_MAX = 512
/** `musicalKey` 的 `@Size(max=8)` */
export const MUSICAL_KEY_MAX = 8
/** `MaterialUpsert.license` 的 `@Size(max=64)` */
export const LICENSE_MAX = 64

// ── Java 字段名 → 表单 field ──────────────────────────────────────────────
//
// ⚠️ 派发规则：`ConsoleContentWriteController` 的请求体带 `@Valid`，而
// `ConsoleExceptionHandler` **没有**声明 `MethodArgumentNotValidException`，于是校验失败落到
// `GlobalExceptionHandler.handleFallback`：返回 **42201** + 文案
// `"请求体校验失败：" + 第一个字段名 + " " + 注解默认 message`。
// 字段名是 **Java 属性名**，与表单 key 不一定同名，所以必须走这张表翻译。
//
// 2026-09-10 实测补注：这条链路**曾经是断的** —— `ConsoleExceptionHandler` 当时还带着一个
// `@Order(HIGHEST_PRECEDENCE)` 的兜底 `@ExceptionHandler(Exception.class)`，它在 advice 顺序上
// 压过了全局映射，把控制台路径上的 42201 统一变成了 **500 + 50002**（`docs/51` I-11）。
// 也就是说：本文件下面这套"字段名翻译"在修掉那个兜底之前**永远走不到**。
// 现在兜底已删，这条注释描述的派发规则才是真的。

/** 字段元数据表：校验遍历它，错误归位也遍历它 —— 一份声明，两处使用 */
export const FIELD_META = {
  title: { field: 'title', label: '标题', kind: 'text', requiredHint: '不能为空', maxLength: TITLE_MAX },
  artist: { field: 'artist', label: '歌手', kind: 'text', maxLength: TITLE_MAX },
  level: {
    field: 'level',
    label: '难度 / 等级',
    kind: 'int',
    requiredHint: '必填',
    min: 1,
    max: 4,
  },
  durationS: { field: 'durationS', label: '时长（秒）', kind: 'int', min: 0 },
  bpm: { field: 'bpm', label: 'BPM', kind: 'decimal' },
  musicalKey: { field: 'musicalKey', label: '调性', kind: 'text', maxLength: MUSICAL_KEY_MAX },
  audioUrl: {
    field: 'audioUrl',
    label: '音频地址',
    kind: 'text',
    requiredHint: '不能为空',
    maxLength: URL_MAX,
    keywords: ['audioUrl', '音频'],
  },
  lrcUrl: { field: 'lrcUrl', label: 'LRC 文件地址', kind: 'text', maxLength: URL_MAX },
  coverUrl: { field: 'coverUrl', label: '封面地址', kind: 'text', maxLength: URL_MAX },
  interestTags: {
    field: 'interestTags',
    label: '兴趣标签',
    kind: 'json',
    requiredHint: '必须是 JSON 数组文本',
  },
  source: {
    field: 'source',
    label: '版权来源',
    kind: 'enum',
    options: ['public_domain', 'original', 'demo_only'],
  },
  status: {
    field: 'status',
    label: '状态',
    kind: 'enum',
    // 歌曲 / 场景 / 听力素材共用的三态（`PublishService.STATUS_*`）；题库是两态，见 `QUESTION_STATUS_OPTIONS`
    options: ['draft', 'published', 'archived'],
  },
  // 歌曲：LRC 行（发布前置条件，见 §6.1）。field 名叫 `lines` 与 `LrcLine` 数组对齐
  lines: { field: 'lines', label: 'LRC 歌词行', kind: 'list', requiredHint: '至少 1 行（上架前置条件）' },

  // 场景
  sceneType: {
    field: 'sceneType',
    label: '场景类型',
    kind: 'enum',
    requiredHint: '必填',
    options: ['cafe', 'airport', 'interview', 'library', 'other'],
  },
  difficulty: {
    field: 'difficulty',
    label: '难度',
    kind: 'int',
    requiredHint: '必填',
    min: 1,
    max: 4,
  },
  description: { field: 'description', label: '场景描述', kind: 'text', maxLength: URL_MAX },
  systemPrompt: {
    field: 'systemPrompt',
    label: '系统提示词',
    kind: 'text',
    requiredHint: '不能为空',
    keywords: ['systemPrompt'],
  },
  openingLine: {
    field: 'openingLine',
    label: '开场白',
    kind: 'text',
    requiredHint: '不能为空（上架前置条件）',
    keywords: ['openingLine', '开场白'],
  },
  targetCorpus: {
    field: 'targetCorpus',
    label: '目标语料',
    kind: 'lines',
    keywords: ['targetCorpus', '目标语料', '语料'],
  },
  promptVersion: { field: 'promptVersion', label: '提示词版本', kind: 'int', min: 1 },
  estimatedTurns: { field: 'estimatedTurns', label: '预计轮次', kind: 'int', min: 1 },
  estimatedMinutes: { field: 'estimatedMinutes', label: '预计时长（分钟）', kind: 'int', min: 1 },

  // 听力素材
  transcript: {
    field: 'transcript',
    label: '文本',
    kind: 'text',
    keywords: ['transcript', '文本'],
  },
  license: { field: 'license', label: '授权说明', kind: 'text', maxLength: LICENSE_MAX },

  // 题库
  examRevision: {
    field: 'examRevision',
    label: '试卷版本',
    kind: 'int',
    requiredHint: '必填',
    min: 1,
    keywords: ['examRevision', '版本'],
  },
  itemIndex: {
    field: 'itemIndex',
    label: '题号',
    kind: 'int',
    requiredHint: '必填',
    min: 1,
    keywords: ['itemIndex', '题号'],
  },
  kind: { field: 'kind', label: '题目类型', kind: 'enum', requiredHint: '必填', options: ['read', 'qa'] },
  prompt: {
    field: 'prompt',
    label: '题干',
    kind: 'text',
    requiredHint: '不能为空',
    keywords: ['prompt', '题干'],
  },
  referenceAnswer: { field: 'referenceAnswer', label: '参考答案', kind: 'text' },
} as const satisfies Record<string, FormFieldMeta>

/** 取字段元数据（key 未登记时返回 null —— 调用方回落成"整表错误"，不编一个字段名出来） */
export function fieldMeta(key: string): FormFieldMeta | null {
  return (FIELD_META as Record<string, FormFieldMeta>)[key] ?? null
}

/** 全部字段元数据（校验与错误归位遍历用） */
export function allFieldMeta(): FormFieldMeta[] {
  return Object.values(FIELD_META) as FormFieldMeta[]
}

/** 表单**值**的键（= 元数据表的键；`field` 字段与它同名，这里只用它约束调用方） */
export type FormFieldKey = keyof typeof FIELD_META
