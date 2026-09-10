/**
 * 「带原因的二次确认」与「错误呈现」共用助手（docs/50 §11.4 危险操作硬规则 + §9.3 审计纪律）。
 *
 * 为什么放在 `views/content/`：本项目只在 `views/` 子树内新增文件，而 5 个消费者里 4 个（歌曲 /
 * 听力素材 / 场景 / 书籍 / 媒体）都在本目录；`views/system/` 的账号与角色页复用同一份，
 * 避免出现两套「确认框长什么样 / 错误怎么显示」的口径。
 */
import { h, ref } from 'vue'
import { NSelect } from 'naive-ui'
import type { DialogApi, DialogOptions, MessageApi } from 'naive-ui'
import type { VNodeChild } from 'vue'

import { ApiError, ERR } from '@/api'
import type { PublishViolation } from '@/api'

/**
 * 下拉选项。刻意用 `type` 而不是 `interface`：naive-ui 的 `SelectBaseOption` 带
 * `[k: string]: unknown` 索引签名，interface 不满足它（TS 只在对象类型别名上给隐式索引签名）。
 */
export type ReasonOption = { label: string; value: string }

/**
 * 操作原因枚举（docs/50 §11.4：下架 / 隐藏 / 停用等状态变更必须选原因）。
 *
 * ⚠️ 已知契约缺口：`POST /content/{domain}/{id}/publish` 的 body 只有 `{status}`
 * （docs/50 §10.2），Python 侧 `publishBook` / `hideMedia`、Java 侧 `revokeAdminSessions`
 * 同样不收原因参数。因此这里选的原因**不会随请求下发**，只用于操作人自我确认；
 * 审计留痕由服务端自己写（docs/50 §9.3）。若要让原因进审计，需先扩契约再改本文件。
 */
export const PUBLISH_REASONS: ReasonOption[] = [
  { label: '运营排期', value: 'schedule' },
  { label: '内容修订完成', value: 'revision_done' },
  { label: '合规复核通过', value: 'compliance_ok' },
  { label: '重新上架', value: 're_online' },
]

export const UNPUBLISH_REASONS: ReasonOption[] = [
  { label: '运营排期', value: 'schedule' },
  { label: '版权到期', value: 'copyright_expired' },
  { label: '内容修订', value: 'content_revision' },
  { label: '合规要求', value: 'compliance' },
  { label: '质量问题', value: 'quality_issue' },
]

export const MEDIA_HIDE_REASONS: ReasonOption[] = [
  { label: '合规要求', value: 'compliance' },
  { label: '用户举报', value: 'user_report' },
  { label: '版权争议', value: 'copyright_dispute' },
  { label: '内容质量', value: 'quality_issue' },
]

export const MEDIA_RESTORE_REASONS: ReasonOption[] = [
  { label: '申诉通过', value: 'appeal_accepted' },
  { label: '误判恢复', value: 'misjudgement' },
  { label: '复核通过', value: 'review_passed' },
]

/** 强制下线 / 编辑账号 / 重置口令 / 删除角色：原因同样进不了请求体，理由见上方缺口说明 */
export const ADMIN_SECURITY_REASONS: ReasonOption[] = [
  { label: '安全事件处置', value: 'security_incident' },
  { label: '权限变更', value: 'role_change' },
  { label: '账号停用', value: 'account_disabled' },
  { label: '本人申请', value: 'self_request' },
  { label: '岗位交接', value: 'handover' },
]

export const ADMIN_UPDATE_REASONS: ReasonOption[] = [
  { label: '岗位调整', value: 'role_change' },
  { label: '姓名更正', value: 'display_name_fix' },
  { label: '账号停用 / 恢复', value: 'status_change' },
  { label: '其他', value: 'other' },
]

export const ROLE_DELETE_REASONS: ReasonOption[] = [
  { label: '岗位撤销', value: 'position_removed' },
  { label: '职责合并', value: 'merged' },
  { label: '误建清理', value: 'created_by_mistake' },
  { label: '其他', value: 'other' },
]

export const ROLE_PERMISSION_REASONS: ReasonOption[] = [
  { label: '职责调整', value: 'duty_change' },
  { label: '最小权限收敛', value: 'least_privilege' },
  { label: '临时授权', value: 'temporary_grant' },
  { label: '流程变更', value: 'process_change' },
  { label: '其他', value: 'other' },
]

export const ROLE_EDIT_REASONS: ReasonOption[] = [
  { label: '职责调整', value: 'duty_change' },
  { label: '名称 / 描述更正', value: 'description_fix' },
  { label: '流程变更', value: 'process_change' },
  { label: '其他', value: 'other' },
]

/**
 * 题目归档（`DELETE /content/questions/{id}` → `status='archived'`）。
 *
 * 为什么题库没有"上架"原因集：题库**没有** `content:question:publish` 权限码，
 * `QuestionUpsert.status` 的取值域也只有 `published|archived`（无 draft）——
 * 题目是"启用 / 归档"两态，不是三态的上下架语义（那三态属于歌曲 / 场景 / 听力素材）。
 */
export const QUESTION_ARCHIVE_REASONS: ReasonOption[] = [
  { label: '题目有误', value: 'item_error' },
  { label: '版本迭代（换新卷）', value: 'revision_bump' },
  { label: '难度不合适', value: 'difficulty_mismatch' },
  { label: '重复题目', value: 'duplicate' },
]

/** 确认框里对「原因去哪了」的一句话说明，避免运营以为它没被记下来 */
const REASON_HINT = '原因用于本次操作确认；状态变更由服务端自动写审计流水（docs/50 §9.3）。'

export interface ActionFailure {
  message: string
  code: number | null
  /** 46002 时服务端回传的所需权限码（docs/50 §10.4） */
  required: string | null
  /** 46011 时的字段级校验原因（docs/50 §6.1） */
  violations: PublishViolation[]
}

/** 把任意异常归一成"能直接显示"的结构：错误码 / 所需权限 / 字段级违规 */
export function describeActionError(err: unknown): ActionFailure {
  if (!(err instanceof ApiError)) {
    const fallback = err instanceof Error ? err.message : String(err)
    return { message: fallback || '操作失败', code: null, required: null, violations: [] }
  }
  const data = (err.data ?? {}) as { required?: unknown; violations?: unknown }
  const raw = Array.isArray(data.violations) ? (data.violations as PublishViolation[]) : []
  return {
    message: err.message || '操作失败',
    code: err.code,
    required: typeof data.required === 'string' ? data.required : null,
    violations: raw.filter(
      (v) => Boolean(v) && typeof v.field === 'string' && typeof (v as { message?: unknown }).message === 'string',
    ),
  }
}

/**
 * 错误 → 展示行。三条硬要求（任务书 + docs/50 §10.4）：
 * 1. 永远先给 `err.message`，不吞原始信息；
 * 2. 46002 且 `data.required` 存在时，明说缺哪个权限码；
 * 3. 46011 时把 `violations[]` 逐字段列出——运营要一次看到"缺什么"，而不是逐个试（§6.1）。
 */
export function failureLines(f: ActionFailure): string[] {
  const lines = [f.message]
  if (f.code === ERR.PERMISSION_DENIED) {
    lines.push(f.required ? `缺少权限码：${f.required}` : '权限不足（服务端未回传所需权限码）')
  }
  if (f.code === ERR.PUBLISH_VALIDATION_FAILED) {
    if (f.violations.length === 0) lines.push('上架校验未通过，但服务端未回传字段级原因（data.violations 为空）')
    // 形状与 Java `PublishService.Violation(field, code, message)` 逐字对齐。
    // 早期实现按 `{field, reason}` 读 → message 永远读不到，页面只显示 `· lrc：undefined`。
    // code 是给排查用的机器可读标识（如 lrc_missing），message 是给人看的原因。
    for (const v of f.violations) {
      lines.push(v.code ? `· ${v.field}（${v.code}）：${v.message}` : `· ${v.field}：${v.message}`)
    }
  }
  if (f.code !== null && f.code > 0) lines.push(`错误码 ${f.code}`)
  return lines
}

/** 失败弹窗：字段级原因用文本插值渲染（绝不 v-html，docs/50 §11.4） */
export function showActionFailure(dialog: DialogApi, failure: ActionFailure): void {
  const title = failure.code === ERR.PUBLISH_VALIDATION_FAILED ? '上架校验未通过' : '操作失败'
  dialog.error({
    title,
    content: () =>
      h(
        'div',
        failureLines(failure).map((line, index) =>
          h('p', { class: index === 0 ? 'm-0 mb-2' : 'm-0 mb-1 text-13px c-muted' }, line),
        ),
      ),
    positiveText: '知道了',
  })
}

export interface ConfirmReasonContext {
  dialog: DialogApi
  message: MessageApi
}

export interface ConfirmReasonOptions {
  title: string
  /** 这次操作会发生什么（含"下架不会被用户侧读到"这类已知缺口提示） */
  detail: string
  reasons: ReasonOption[]
  positiveText: string
  successText: string
  /** true = 危险操作，用警示色弹窗（下架 / 隐藏 / 停用 / 删除 / 强制下线） */
  danger?: boolean
  /** 追加的警示文本，如已知缺口说明 */
  note?: string
  submit: () => Promise<unknown>
  onSuccess?: () => void
  onFailure?: (failure: ActionFailure) => void
}

/** 确认框正文：说明 + 原因必选 + 口径提示 */
function confirmBody(opts: ConfirmReasonOptions, reason: { value: string | null }): VNodeChild {
  const nodes: VNodeChild[] = [h('p', { class: 'm-0 c-muted' }, opts.detail)]
  if (opts.note) nodes.push(h('p', { class: 'm-0 mt-2 text-12px', style: 'color: var(--c-warn)' }, opts.note))
  nodes.push(
    h('div', { class: 'mt-3' }, [
      h('div', { class: 'c-muted text-12px mb-1' }, '操作原因（必填）'),
      h(NSelect, {
        value: reason.value,
        options: opts.reasons,
        placeholder: '请选择操作原因',
        consistentMenuWidth: false,
        'onUpdate:value': (value: string | null) => {
          reason.value = value
        },
      }),
    ]),
  )
  nodes.push(h('p', { class: 'm-0 mt-2 c-weak text-12px' }, REASON_HINT))
  return h('div', nodes)
}

/**
 * 统一的"确认 + 原因 + 提交 + 错误呈现"入口。
 * 失败时**关掉确认框**再弹错误：留着确认框会让人以为"再点一次就能过"，
 * 而 46011 / 46002 都得先去补内容或换账号才行。未选原因则返回 false 阻止关闭。
 */
export function confirmWithReason(ctx: ConfirmReasonContext, opts: ConfirmReasonOptions): void {
  const reason = ref<string | null>(null)
  const options: DialogOptions = {
    title: opts.title,
    content: () => confirmBody(opts, reason),
    positiveText: opts.positiveText,
    negativeText: '取消',
    onPositiveClick: async () => {
      if (!reason.value) {
        ctx.message.warning('请先选择操作原因')
        return false
      }
      try {
        await opts.submit()
      } catch (err) {
        const failure = describeActionError(err)
        showActionFailure(ctx.dialog, failure)
        opts.onFailure?.(failure)
        return true
      }
      ctx.message.success(opts.successText)
      opts.onSuccess?.()
      return true
    },
  }
  if (opts.danger) ctx.dialog.warning(options)
  else ctx.dialog.info(options)
}
