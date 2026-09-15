/**
 * 服务端校验错误 → **表单字段**（本文件是"422/46007 必须落回出错的输入框"这条要求的实现）。
 *
 * <h2>为什么不能只 toast 一句 message</h2>
 * 写端点的入参校验全部来自 `ConsoleContentWriteController` 的 record 注解（`@NotBlank` /
 * `@Size` / `@Min` / `@Pattern`）。一次提交可能有**多个**字段不合法，而
 * `GlobalExceptionHandler.handleFallback` 只挑**第一个** `fieldError` 拼进 message
 * （`.limit(1)` + 前缀 `"请求体校验失败："`）—— 于是运营点一次"保存"只看到一条，
 * 修完再点又冒出下一条。本模块把 message 里那个 Java 属性名解析出来，定位到具体输入框，
 * 并把原始文案并排显示（不吞服务端原话）。
 *
 * <h2>两条链路的形状差异（实测自源码，不是猜的）</h2>
 * - **Bean Validation 失败**（`@Valid` 请求体）→ `GlobalExceptionHandler` 兜底分支 →
 *   `42201` + message 前缀 `请求体校验失败：`，格式 `{Java属性名} {注解默认message}`。
 * - **业务拒绝**（`ConsoleException`）→ `ConsoleExceptionHandler` →
 *   `46007`（入参非法，如题库 `itemIndex` 撞车）/ `46009`（目标不存在，如 `PUT` 一个已删的 id），
 *   message 是服务端自己写的中文，**没有字段名** —— 只能按关键词归位。
 * - `46011` + `data.violations[]` 是**上架**校验的形状，不由本模块处理
 *   （上架走 `actionReason.describeActionError`；这里兼容它只是为了"同一弹窗里改完直接上架"
 *   时也能把 `field` 落回表单）。
 */

import { ApiError, ERR } from '@/api'
import type { PublishViolation } from '@/api'
import { allFieldMeta, fieldMeta } from './formMeta'
import type { FormFieldKey } from './formMeta'
import type { FormErrors } from './contentFormTypes'

/** 服务端 Bean Validation 失败的 message 前缀（`GlobalExceptionHandler.handleFallback`） */
const VALIDATION_PREFIX = '请求体校验失败：'

/**
 * 服务端会报、但**表单里没有对应输入框**的字段 → 给运营的解释。
 *
 * 字段名与表单 key 的同名映射**不写表**（写表就会漏字段、且两处必须同步改）：
 * 归位时用 `isFormFieldKey()` 判定 —— 只有这张"表单真的没有这个输入框"的名单才需要人工维护。
 *
 * `pitchRefStatus`：歌曲没有这个输入框（它是 Python 离线任务的产物，不是人填的）。
 * 但 `applySong` 在提交体里没带该字段时会把它重置为 `missing`，而"参考旋律未就绪"
 * 正是上架校验会拦的项 —— 所以这条不归到任何输入框，而是**如实提示下游影响**。
 */
export const REMOTE_FIELDS: Record<string, string> = {
  pitchRefStatus:
    '参考旋律状态由 Python 离线任务写入（`song_pitch_refs` 归 Python 写），控制台不提供手工编辑；' +
    '请先补齐 LRC 并等待离线提取任务完成（PublishService.validateSong 要求 ready）。',
}

/** 解析结果：落到哪个字段 + 服务端原文（原文里已剥掉前缀，因为前缀对外是噪音） */
export interface ParsedServerError {
  field: FormFieldKey | null
  /** true = 该字段是"服务端管、表单没有"的（见 `REMOTE_FIELDS`） */
  remote: boolean
  message: string
  code: number
}

/**
 * 从 message 里解析 Java 属性名。
 *
 * 只认**前缀 + 首词**：`请求体校验失败：audioUrl must not be blank` → `audioUrl`。
 * 不做模糊匹配 —— 猜错字段比不归位更糟（运营会盯着一个没错的框反复改）。
 */
export function parseJavaFieldError(message: string): { field: string | null; rest: string } {
  const text = message.trim()
  if (!text.startsWith(VALIDATION_PREFIX)) return { field: null, rest: text }
  const body = text.slice(VALIDATION_PREFIX.length).trim()
  const space = body.search(/\s/)
  if (space <= 0) return { field: null, rest: body }
  return { field: body.slice(0, space), rest: body.slice(space + 1).trim() }
}

/** 按关键词找字段（46007/46009 这类没有字段名的业务拒绝） */
function fieldByKeyword(message: string): FormFieldKey | null {
  for (const meta of allFieldMeta()) {
    if (!meta.keywords) continue
    if (!meta.keywords.some((word) => message.includes(word))) continue
    // 元数据表是 `as const`，但 `allFieldMeta()` 的返回类型把 key 拓宽成 string；
    // 这里用**登记的 key 判定**收窄，而不是 `as` 断言（断言会掩盖"关键词指向了不存在的字段"）
    return isFormFieldKey(meta.field) ? meta.field : null
  }
  return null
}

/** 该字符串是不是一个已登记的表单字段 key（收窄用，不做断言） */
function isFormFieldKey(value: string): value is FormFieldKey {
  return fieldMeta(value) !== null
}

/**
 * 任意异常 → 归一化的服务端错误。**不改动异常**，只读。
 *
 * `46002`（缺权限码）不当字段错误：它是账号级问题，归位到某个输入框只会误导
 * （`describeActionError` + `failureLines` 会明说缺哪个权限码，由弹窗顶部的错误条呈现）。
 */
export function parseServerError(err: unknown): ParsedServerError {
  if (!(err instanceof ApiError)) {
    return { field: null, remote: false, message: err instanceof Error ? err.message : String(err), code: 0 }
  }
  const { field: javaField, rest } = parseJavaFieldError(err.message)
  if (javaField) {
    if (REMOTE_FIELDS[javaField]) {
      return { field: null, remote: true, message: `${rest}（${REMOTE_FIELDS[javaField]}）`, code: err.code }
    }
    // 归位规则：Java 属性名几乎都与表单 key 同名（例外是 `pitchRefStatus`，已进 REMOTE_FIELDS）。
    // 用 `isFormFieldKey` 判定而不是 `as FormFieldKey` —— 断言会把"服务端报了新字段、
    // 前端根本没这个输入框"这种**真实缺口**掩盖成"归位成功但永远没人标红"。
    return { field: isFormFieldKey(javaField) ? javaField : null, remote: false, message: rest || err.message, code: err.code }
  }
  // 没有字段名：先按关键词归位（如 "同一版本内 itemIndex 已存在：1/2"），仍找不到就交给整表错误条
  return { field: fieldByKeyword(err.message), remote: false, message: err.message, code: err.code }
}

/** `data.violations[]`（46011 上架校验的形状）→ 表单错误：字段名与 Java 属性同名 */
export function errorsFromViolations(violations: PublishViolation[]): FormErrors {
  const errors: FormErrors = {}
  for (const violation of violations) {
    if (isFormFieldKey(violation.field)) errors[violation.field] = violation.message
    else if (REMOTE_FIELDS[violation.field]) errors.form = `${REMOTE_FIELDS[violation.field]}（${violation.message}）`
    else errors.form = errors.form ?? `${violation.field}：${violation.message}`
  }
  return errors
}

/**
 * 异常 → 表单错误表 + 是否已归位到具体输入框。
 *
 * `mapped=false` 表示"没有具体字段可标红"，调用方应把 message 放进弹窗底部的错误里
 * （仍然显示，绝不静默）。`46011` 的 `data.violations` 会被展开成多条字段错误。
 */
export function formErrorsFromError(err: unknown): { errors: FormErrors; mapped: boolean } {
  if (err instanceof ApiError && err.code === ERR.PUBLISH_VALIDATION_FAILED) {
    const data = (err.data ?? {}) as { violations?: unknown }
    const list = Array.isArray(data.violations) ? (data.violations as PublishViolation[]) : []
    const fromViolations = errorsFromViolations(list)
    return { errors: fromViolations, mapped: Object.keys(fromViolations).length > 0 }
  }
  const parsed = parseServerError(err)
  if (parsed.field) {
    // 表单 key 与 Java 属性名同名时才能直接落格；LRC 行类错误（lines）落整表
    return { errors: { [parsed.field]: parsed.message }, mapped: true }
  }
  return { errors: { form: parsed.message }, mapped: false }
}
