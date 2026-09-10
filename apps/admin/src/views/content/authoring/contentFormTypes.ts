/**
 * 内容写入表单的**值类型与字段级契约**（纯类型 + 两个纯函数，不依赖 Vue —— 可被单测直接调用）。
 *
 * 三层口径，逐条对着 `ConsoleContentWriteController` 的 record 写：
 * 1. **表单值一律是字符串**（naive-ui 的 `n-input` 只吐字符串；数字下拉用 number）。
 *    转换只在 `contentFormPayload.ts` 的 `toXxxUpsert` 一处发生 —— 分散转换必然出现
 *    "某个页面忘了 trim / 忘了转数字"。
 * 2. **空的可选字段发 `null` 而不是 `""`**：`""` 会被服务端当成真实值写库
 *    （`applySong` 直接 `e.setArtist("")`），而 `null` 才是"没有值"（库里这些列可空）。
 * 3. **必填的 `@NotNull` 字段（`level`/`difficulty`/`examRevision`/`itemIndex`）不能发 null**：
 *    发 null 会吃 42201（`@NotNull` 的默认 message 读起来像"不能为 null"，运营看不懂）。
 *
 * 本模块原是 665 行的单文件 `contentFormPayload.ts`，触发 ESLint `max-lines`（350）门禁。
 * 拆分按**改动原因**切，不按行数平均切：
 * - `contentFormTypes.ts`（本文件）：服务端 record 变了才会改；
 * - `contentFormModel.ts`：空值默认与本地预检规矩变了才会改；
 * - `contentFormPayload.ts`：提交口径（表单 → 线格式）变了才会改。
 * 三层里只有第二层是"前端自己的规矩"，第一、三层是服务端契约的镜像 —— 分开之后，
 * 审阅时一眼能看出某次改动动的是契约还是本地校验。
 */

import type {
  ContentStatus,
  QuestionKind,
  SceneType,
  SongSource,
} from '@/api'
import type { FormFieldKey } from './formMeta'

// ── 更新体：字段类型「值 + 缺省」 ────────────────────────────────────────
//
// 为什么不是直接复用 `SongUpsert` 再全发：见 `songUpsertFromForm` 的长注释（漏字段会被
// 服务端按默认值覆盖）。这里用类型把"可以留空 = 服务端保持原值"显式表达出来，
// 调用方（弹窗）不需要知道哪几个字段是可空——类型会强制它处理。

/** 更新体字段：有值 = 改成这个值；`null` = **保持原值**（服务端 record 允许 null 的字段才有此语义） */
type Patched<T> = T | null

/** 歌曲更新体 */
export interface SongUpsertPatch {
  title: Patched<string>
  artist: Patched<string | null>
  level: Patched<number>
  durationS: Patched<number | null>
  bpm: Patched<number | null>
  musicalKey: Patched<string | null>
  audioUrl: Patched<string>
  lrcUrl: Patched<string | null>
  coverUrl: Patched<string | null>
  interestTags: Patched<string | null>
  source: Patched<SongSource | null>
  status: Patched<ContentStatus | null>
}

/** 场景更新体 */
export interface ScenarioUpsertPatch {
  title: Patched<string>
  sceneType: Patched<SceneType>
  difficulty: Patched<number>
  description: Patched<string | null>
  systemPrompt: Patched<string>
  openingLine: Patched<string>
  targetCorpus: Patched<string | null>
  interestTags: Patched<string | null>
  promptVersion: Patched<number | null>
  estimatedTurns: Patched<number | null>
  estimatedMinutes: Patched<number | null>
  status: Patched<ContentStatus | null>
}

/** 听力素材更新体 */
export interface MaterialUpsertPatch {
  title: Patched<string>
  level: Patched<number>
  audioUrl: Patched<string>
  durationS: Patched<number | null>
  transcript: Patched<string | null>
  interestTags: Patched<string | null>
  source: Patched<SongSource | null>
  license: Patched<string | null>
  status: Patched<ContentStatus | null>
}

/** 题目更新体（`QuestionPatch`）：身份字段（版本 / 题号）后端不接受，故不在其中 */
export interface QuestionPatchBody {
  prompt: Patched<string>
  referenceAnswer: Patched<string | null>
  status: Patched<'published' | 'archived'>
}

/** 值相等比较（trim 后比较：只差首尾空格不算改动，避免制造无意义的审计流水） */
export function sameValue(left: unknown, right: unknown): boolean {
  if (left === right) return true
  const l = typeof left === 'string' ? left.trim() : left
  const r = typeof right === 'string' ? right.trim() : right
  return l === r
}

/** 一个字段的单片更新体：改了发新值，没改发 null（= 服务端保持原值） */
export function patchOf<T>(next: T, prev: T): Patched<T> {
  return sameValue(next, prev) ? null : next
}

/**
 * 表单错误表（field → 提示语）；`form` 是"没有具体字段"的整表错误。
 *
 * 含 LRC 三个行级 key（`offsetMs` / `endOffsetMs` / `lineText`）：它们不在 `FIELD_META` 里
 * （LRC 行是数组，逐行校验走 `validateLrcRows`，不走按字段的元数据遍历）。
 */
export type FormErrors = Partial<
  Record<FormFieldKey | 'form' | 'offsetMs' | 'endOffsetMs' | 'lineText', string>
>

/** 表单的数字字段统一用字符串存（`''` = 未填），空值语义见文件头第 2 条 */
export interface SongForm {
  title: string
  artist: string
  level: number | null
  durationS: string
  bpm: string
  musicalKey: string
  audioUrl: string
  lrcUrl: string
  coverUrl: string
  interestTags: string
  source: SongSource
  status: ContentStatus
}

/** LRC 一行（`LrcLine`）：时间与文本都是字符串，提交时转数字 */
export interface LrcFormRow {
  offsetMs: string
  endOffsetMs: string
  lineText: string
}

export interface ScenarioForm {
  title: string
  sceneType: SceneType | null
  difficulty: number | null
  description: string
  systemPrompt: string
  openingLine: string
  targetCorpus: string
  interestTags: string
  promptVersion: string
  estimatedTurns: string
  estimatedMinutes: string
  status: ContentStatus
}

export interface MaterialForm {
  title: string
  level: number | null
  audioUrl: string
  durationS: string
  transcript: string
  interestTags: string
  source: SongSource
  license: string
  status: ContentStatus
}

export interface QuestionForm {
  examRevision: string
  itemIndex: string
  kind: QuestionKind | null
  prompt: string
  referenceAnswer: string
  status: 'published' | 'archived'
}
