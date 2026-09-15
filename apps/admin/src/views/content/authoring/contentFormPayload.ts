/**
 * 内容写入表单的 **payload 映射层**（表单值 → 线格式，纯函数，不依赖 Vue）。
 *
 * 三层口径与拆分理由见 `contentFormTypes.ts` 文件头；本文件只负责"发什么"：
 * - `fillXxxForm`：详情 → 表单值（回读）；
 * - `toXxxUpsert` / `toXxxPatch`：表单 → 新建体 / 更新体；
 * - `xxxFromForm`：更新时**只发真的改过的字段**。
 */

import type {
  ContentStatus,
  LrcUpsert,
  MaterialDetail,
  MaterialUpsert,
  QuestionDetail,
  QuestionKind,
  QuestionPatch,
  QuestionUpsert,
  SceneType,
  ScenarioDetail,
  ScenarioUpsert,
  SongDetail,
  SongSource,
  SongUpsert,
} from '@/api'
import { parseDecimal, parseWhole, trimmedOrNull } from './contentFormModel'
import { patchOf } from './contentFormTypes'
import type {
  LrcFormRow,
  MaterialForm,
  MaterialUpsertPatch,
  QuestionForm,
  QuestionPatchBody,
  ScenarioForm,
  ScenarioUpsertPatch,
  SongForm,
  SongUpsertPatch,
} from './contentFormTypes'

/**
 * 把单条详情回填成表单值（`null` → 空串：输入框只认字符串，`null` 会让 naive-ui 显示 "null"）。
 *
 * 为什么不直接拿列表行回填：列表行（`SongRow` 等）只投影了 6 个字段，
 * 用它回填会让没投影的字段变成空串，下一次 PUT 就把库里的值清掉。
 */
export function fillSongForm(detail: SongDetail): SongForm {
  return {
    title: detail.title ?? '',
    artist: detail.artist ?? '',
    level: detail.level ?? null,
    durationS: detail.durationS === null ? '' : String(detail.durationS),
    bpm: detail.bpm === null ? '' : String(detail.bpm),
    musicalKey: detail.musicalKey ?? '',
    audioUrl: detail.audioUrl ?? '',
    lrcUrl: detail.lrcUrl ?? '',
    coverUrl: detail.coverUrl ?? '',
    interestTags: detail.interestTags ?? '',
    source: (detail.source as SongSource | null) ?? 'public_domain',
    status: (detail.status as ContentStatus | null) ?? 'draft',
  }
}

export function fillScenarioForm(detail: ScenarioDetail): ScenarioForm {
  return {
    title: detail.title ?? '',
    sceneType: (detail.sceneType as SceneType | null) ?? null,
    difficulty: detail.difficulty ?? null,
    description: detail.description ?? '',
    systemPrompt: detail.systemPrompt ?? '',
    openingLine: detail.openingLine ?? '',
    targetCorpus: detail.targetCorpus ?? '',
    interestTags: detail.interestTags ?? '',
    promptVersion: detail.promptVersion === null ? '' : String(detail.promptVersion),
    estimatedTurns: detail.estimatedTurns === null ? '' : String(detail.estimatedTurns),
    estimatedMinutes: detail.estimatedMinutes === null ? '' : String(detail.estimatedMinutes),
    status: (detail.status as ContentStatus | null) ?? 'draft',
  }
}

export function fillMaterialForm(detail: MaterialDetail): MaterialForm {
  return {
    title: detail.title ?? '',
    level: detail.level ?? null,
    audioUrl: detail.audioUrl ?? '',
    durationS: detail.durationS === null ? '' : String(detail.durationS),
    transcript: detail.transcript ?? '',
    interestTags: detail.interestTags ?? '',
    source: (detail.source as SongSource | null) ?? 'public_domain',
    license: detail.license ?? '',
    status: (detail.status as ContentStatus | null) ?? 'draft',
  }
}

export function fillQuestionForm(detail: QuestionDetail): QuestionForm {
  return {
    examRevision: String(detail.examRevision),
    itemIndex: String(detail.itemIndex),
    kind: (detail.kind as QuestionKind | null) ?? 'read',
    prompt: detail.prompt ?? '',
    referenceAnswer: detail.referenceAnswer ?? '',
    status: detail.status === 'archived' ? 'archived' : 'published',
  }
}

/**
 * 更新时**只发真的改过的字段**（其余字段留 null，由服务端保留原值）。
 *
 * 为什么必须这么做（这是本模块最重要的一条设计）：
 * `applySong` 对 null 字段一律回落默认值 —— `status → draft`、`source → public_domain`、
 * `interestTags → "[]"`、`pitchRefStatus → missing`。若把整个表单原样发回，
 * 运营只是改一个"歌手"，服务端收到 `source=null` 也会把版权来源重置成 `public_domain`；
 * 更糟的是 `pitchRefStatus=null` 会把已就绪的参考旋律置回 missing，直接让这首歌**无法上架**
 * （`PublishService.validateSong` 要求 `ready`）。只发变更字段是唯一安全的口径。
 *
 * ⚠️ 已知服务端形状缺口（**报告，未改**）：`SongUpsert` 等 record **没有** `@JsonInclude(NON_NULL)`
 * 之类的"缺省即不变"语义，全部靠 `applyXxx` 里的 null 三元判断实现。
 * 因此"留空 = 不改"这条路只在服务端显式写了 null 分支的字段上成立；
 * 新增字段时若忘了写 null 分支，本模块的"只发变更"会变成"新增字段永远发不出去"。
 */
export function songUpsertFromForm(form: SongForm, original: SongForm | null): SongUpsertPatch {
  const next = toSongUpsert(form)
  if (original === null) return next
  const base = toSongUpsert(original)
  return {
    title: patchOf(next.title, base.title),
    artist: patchOf(next.artist, base.artist),
    level: patchOf(next.level, base.level),
    durationS: patchOf(next.durationS, base.durationS),
    bpm: patchOf(next.bpm, base.bpm),
    musicalKey: patchOf(next.musicalKey, base.musicalKey),
    audioUrl: patchOf(next.audioUrl, base.audioUrl),
    lrcUrl: patchOf(next.lrcUrl, base.lrcUrl),
    coverUrl: patchOf(next.coverUrl, base.coverUrl),
    interestTags: patchOf(next.interestTags, base.interestTags),
    source: patchOf(next.source, base.source),
    status: patchOf(next.status, base.status),
  }
}

/** 场景：同上，未改动字段发 null */
export function scenarioUpsertFromForm(
  form: ScenarioForm,
  original: ScenarioForm | null,
): ScenarioUpsertPatch {
  const next = toScenarioUpsert(form)
  if (original === null) return next
  const base = toScenarioUpsert(original)
  return {
    title: patchOf(next.title, base.title),
    sceneType: patchOf(next.sceneType, base.sceneType),
    difficulty: patchOf(next.difficulty, base.difficulty),
    description: patchOf(next.description, base.description),
    systemPrompt: patchOf(next.systemPrompt, base.systemPrompt),
    openingLine: patchOf(next.openingLine, base.openingLine),
    targetCorpus: patchOf(next.targetCorpus, base.targetCorpus),
    interestTags: patchOf(next.interestTags, base.interestTags),
    promptVersion: patchOf(next.promptVersion, base.promptVersion),
    estimatedTurns: patchOf(next.estimatedTurns, base.estimatedTurns),
    estimatedMinutes: patchOf(next.estimatedMinutes, base.estimatedMinutes),
    status: patchOf(next.status, base.status),
  }
}

/** 听力素材：同上，未改动字段发 null */
export function materialUpsertFromForm(
  form: MaterialForm,
  original: MaterialForm | null,
): MaterialUpsertPatch {
  const next = toMaterialUpsert(form)
  if (original === null) return next
  const base = toMaterialUpsert(original)
  return {
    title: patchOf(next.title, base.title),
    level: patchOf(next.level, base.level),
    audioUrl: patchOf(next.audioUrl, base.audioUrl),
    durationS: patchOf(next.durationS, base.durationS),
    transcript: patchOf(next.transcript, base.transcript),
    interestTags: patchOf(next.interestTags, base.interestTags),
    source: patchOf(next.source, base.source),
    license: patchOf(next.license, base.license),
    status: patchOf(next.status, base.status),
  }
}

/** 题目：`QuestionPatch` 支持面只有题干 / 参考答案 / 状态，未改动字段发 null */
export function questionPatchFromForm(
  form: QuestionForm,
  original: QuestionForm | null,
): QuestionPatchBody {
  const next = toQuestionPatch(form)
  if (original === null) return next
  const base = toQuestionPatch(original)
  return {
    prompt: patchOf(next.prompt, base.prompt),
    referenceAnswer: patchOf(next.referenceAnswer, base.referenceAnswer),
    status: patchOf(next.status, base.status),
  }
}

/** 表单 → 新建体（歌曲）：**全量**（新建没有"原值"可保持），空可选字段发 null 而不是 "" */
export function toSongUpsert(form: SongForm): SongUpsert {
  return {
    title: form.title.trim(),
    artist: trimmedOrNull(form.artist),
    // level 是 `@NotNull`：下拉必选，本地预检已拦住 null；这里回落 1 只是让类型收敛
    level: form.level ?? 1,
    durationS: parseWhole(form.durationS) ?? null,
    bpm: parseDecimal(form.bpm) ?? null,
    musicalKey: trimmedOrNull(form.musicalKey),
    audioUrl: form.audioUrl.trim(),
    lrcUrl: trimmedOrNull(form.lrcUrl),
    coverUrl: trimmedOrNull(form.coverUrl),
    interestTags: trimmedOrNull(form.interestTags),
    source: form.source,
    status: form.status,
  }
}

/** 表单 → 新建体（场景） */
export function toScenarioUpsert(form: ScenarioForm): ScenarioUpsert {
  return {
    title: form.title.trim(),
    sceneType: form.sceneType ?? 'other',
    difficulty: form.difficulty ?? 1,
    description: trimmedOrNull(form.description),
    systemPrompt: form.systemPrompt.trim(),
    openingLine: form.openingLine.trim(),
    targetCorpus: trimmedOrNull(form.targetCorpus),
    interestTags: trimmedOrNull(form.interestTags),
    promptVersion: parseWhole(form.promptVersion) ?? null,
    estimatedTurns: parseWhole(form.estimatedTurns) ?? null,
    estimatedMinutes: parseWhole(form.estimatedMinutes) ?? null,
    status: form.status,
  }
}

/** 表单 → 新建体（听力素材） */
export function toMaterialUpsert(form: MaterialForm): MaterialUpsert {
  return {
    title: form.title.trim(),
    level: form.level ?? 1,
    audioUrl: form.audioUrl.trim(),
    durationS: parseWhole(form.durationS) ?? null,
    transcript: trimmedOrNull(form.transcript),
    interestTags: trimmedOrNull(form.interestTags),
    source: form.source,
    license: trimmedOrNull(form.license),
    status: form.status,
  }
}

/** 表单 → 新建体（题目）：版本号与题号只在新建时可定（`QuestionUpsert`） */
export function toQuestionUpsert(form: QuestionForm): QuestionUpsert {
  return {
    examRevision: parseWhole(form.examRevision) ?? 1,
    itemIndex: parseWhole(form.itemIndex) ?? 1,
    kind: form.kind ?? 'read',
    prompt: form.prompt.trim(),
    referenceAnswer: trimmedOrNull(form.referenceAnswer),
    status: form.status,
  }
}

/** 编辑态体（`QuestionPatch`）：身份字段（版本 / 题号）不在其中 —— 后端不接受 */
export function toQuestionPatch(form: QuestionForm): QuestionPatch {
  return {
    prompt: form.prompt.trim(),
    referenceAnswer: trimmedOrNull(form.referenceAnswer),
    status: form.status,
  }
}

/**
 * LRC 提交体：**按 `offsetMs` 升序排序后**再发。
 *
 * 为什么排序很重要：服务端 `replaceLrc` 按**数组下标**重排 `seq`（`l.setSeq(seq++)`），
 * 而逐句跟唱评分依赖 `seq` 顺序 —— 乱序提交会让整首歌的歌词与时间轴错位。
 * 同 `offsetMs` 时保持用户录入顺序（`Array.sort` 在 V8 上稳定，但不依赖它：用原始下标兜底）。
 */
export function toLrcUpsert(rows: LrcFormRow[]): LrcUpsert {
  const lines = rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      const left = parseWhole(a.row.offsetMs) ?? 0
      const right = parseWhole(b.row.offsetMs) ?? 0
      return left === right ? a.index - b.index : left - right
    })
    .map(({ row }) => {
      const offsetMs = parseWhole(row.offsetMs) ?? 0
      return {
        offsetMs,
        // 留空 = 与起始同值（零时长行），不发 null —— 该列 NOT NULL
        endOffsetMs: parseWhole(row.endOffsetMs) ?? offsetMs,
        lineText: row.lineText.trim(),
      }
    })
  return { lines }
}

/** 已保存的 LRC → 表单行（数值转字符串，`null` 结束时间回落成空串让运营自己决定） */
export function toLrcFormRows(rows: { offsetMs: number; endOffsetMs: number | null; lineText: string }[]): LrcFormRow[] {
  return rows.map((row) => ({
    offsetMs: String(row.offsetMs),
    endOffsetMs: row.endOffsetMs === null ? '' : String(row.endOffsetMs),
    lineText: row.lineText,
  }))
}
