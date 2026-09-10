/**
 * 审核域共用常量与兜底助手（`QueueView` / `ReportsView` / `ActionsView` / 两个弹窗共用一份）。
 *
 * 为什么单独一个模块：三个页面都要「枚举 → 中文文案」「错误 → 可读提示」这两件事，
 * 各页各写一套必然漂移（同一错误码在两个页面显示不同话术），审查时无法对照（docs/50 §11.3）。
 *
 * 与 `src/api/types.ts` 的**契约缺口**集中在这里兜住，页面侧不再各自猜测：
 * 1. `ModerationCaseRow.assignee` 声明为 `{id, displayName}`，而 Java `ModerationController.CaseView`
 *    实际回传的是 `assigneeId`（数字）；
 * 2. `ModerationStats` 声明的 `approvedToday / rejectedToday / trend / decisions` 在 Java `stats()`
 *    的平铺 Map 里并不存在（只有 pending/escalated/approved/rejected/… 与 byStatus）。
 * 因此一律走本文件的读取函数：拿到就显示、拿不到显示「—」，**不伪造数字**（docs/50 §11.4）。
 */
import { ApiError, ERR } from '@/api'
import type {
  AuditLogRow,
  ModerationCaseRow,
  ModerationDecision,
  ModerationTargetType,
} from '@/api'

// ── 目标 / 来源 / 优先级 / 状态 ─────────────────────────────────────────────

export const TARGET_TYPE_LABEL: Record<ModerationTargetType, string> = {
  post: '帖子',
  comment: '评论',
  media: '媒体',
  direct_message: '私信',
}

export const TARGET_TYPE_OPTIONS = (Object.keys(TARGET_TYPE_LABEL) as ModerationTargetType[]).map(
  (value) => ({ label: TARGET_TYPE_LABEL[value], value }),
)

export const SOURCE_LABEL: Record<string, string> = {
  auto: '自动',
  report: '举报',
  manual: '人工',
}

export const PRIORITY_LABEL: Record<number, string> = { 1: '高', 2: '中', 3: '低' }

/** 优先级色调（1 高最刺眼）——只用 `c-badge--*` 语义类，不写十六进制（docs/50 §11.2） */
export const PRIORITY_TONE: Record<number, string> = { 1: 'danger', 2: 'warn', 3: 'muted' }

export const PRIORITY_OPTIONS = [1, 2, 3].map((value) => ({
  label: `${PRIORITY_LABEL[value]}（${value}）`,
  value: String(value),
}))

export const CASE_STATUS_OPTIONS = [
  { label: '待处理', value: 'pending' },
  { label: '已升级', value: 'escalated' },
  { label: '已处置', value: 'approved' },
  { label: '已驳回', value: 'rejected' },
  { label: '已撤回', value: 'withdrawn' },
]

/** 举报状态（`StatusBadge` 没有 report 这一 kind，故这里自带 文案 + 色调） */
export const REPORT_STATUS_META: Record<string, { text: string; tone: string }> = {
  pending: { text: '待处理', tone: 'warn' },
  accepted: { text: '已受理', tone: 'ok' },
  rejected: { text: '不成立', tone: 'muted' },
  duplicate: { text: '重复举报', tone: 'muted' },
}

export const REPORT_STATUS_OPTIONS = [
  { label: '待处理', value: 'pending' },
  { label: '已受理', value: 'accepted' },
  { label: '不成立', value: 'rejected' },
  { label: '重复举报', value: 'duplicate' },
]

// ── 原因码（docs/50 §5.3.8；Java `requireReasonCode` 同口径，服务端只认这 9 个） ──

export const REASON_CODE_LABEL: Record<string, string> = {
  spam: '垃圾信息',
  abuse: '辱骂骚扰',
  porn: '色情低俗',
  violence: '暴力血腥',
  politics: '涉政敏感',
  ad: '广告引流',
  copyright: '版权侵权',
  misinfo: '虚假信息',
  other: '其他',
}

export const REASON_CODE_OPTIONS = Object.entries(REASON_CODE_LABEL).map(([value, label]) => ({
  label: `${label}（${value}）`,
  value,
}))

export function reasonCodeText(code: string | null | undefined): string {
  if (!code) return '—'
  return REASON_CODE_LABEL[code] ?? code
}

// ── 决定枚举（docs/50 §6.2 表：决定 → 工单状态 → 对目标表的写入） ────────────

export interface DecisionMeta {
  value: ModerationDecision
  label: string
  /** 「这个决定对内容做了什么」——审核员点之前必须看到的一句话（docs/50 §11.4 危险操作二次确认） */
  effect: string
  /** true = 会让内容对用户不可见（服务端写 status=hidden/deleted） */
  invisible: boolean
}

export const DECISION_META: DecisionMeta[] = [
  {
    value: 'approve',
    label: '通过（内容保留）',
    effect: '目标内容保持现状，用户照常可见；审核单关闭为「已处置」。',
    invisible: false,
  },
  {
    value: 'hide',
    label: '隐藏',
    effect: '目标内容**立即对用户不可见**（含作者本人），数据行保留、点赞与评论计数不变，可恢复。',
    invisible: true,
  },
  {
    value: 'delete',
    label: '删除（软删）',
    effect: '目标内容**立即对用户不可见**，状态置为已删除（软删，不做物理删除）；留行以便追溯。',
    invisible: true,
  },
  {
    value: 'reject',
    label: '驳回（不作为）',
    effect: '不改动内容，判定举报不成立；审核单关闭为「已驳回」。',
    invisible: false,
  },
  {
    value: 'escalate',
    label: '升级',
    effect: '不改动内容，审核单升级并把优先级提到最高，交给更高权限处理，仍留在队列里。',
    invisible: false,
  },
]

export function decisionMeta(value: string | null | undefined): DecisionMeta | null {
  return DECISION_META.find((d) => d.value === value) ?? null
}

// ── 认领人 / 决定人 / 举报数 ───────────────────────────────────────────────
// 2026-09-10 修正：这三处原先用 `as unknown as` 兜底"两种契约形态"——那是**掩盖**不是修复。
// 已核对 Java `ModerationController.CaseView`：认领人/决定人只给**标量 id**，举报数只在 `snapshot`。
// 现在直接按真实字段读，不再有类型逃逸；要显示姓名由调用方在前端 join 管理员列表。

/** 认领人展示：本人「我」，他人 #id（`CaseView` 不带姓名——不编名字） */
export function assigneeText(row: ModerationCaseRow, meId: number | null): string {
  const id = row.assigneeId
  if (id === null || id === undefined) return '未认领'
  return meId !== null && id === meId ? `我（#${id}）` : `#${id}`
}

export function deciderText(row: ModerationCaseRow, meId: number | null): string {
  const id = row.decidedBy
  if (id === null || id === undefined) return '—'
  return meId !== null && id === meId ? `我（#${id}）` : `#${id}`
}

/** 举报数：`CaseView` 顶层没有该字段，只有 `snapshot.reportCount` 有值；没有则「—」 */
export function reportCountText(row: ModerationCaseRow): string {
  const value = row.snapshot?.reportCount
  return typeof value === 'number' ? String(value) : '—'
}

export function targetText(row: Pick<ModerationCaseRow, 'targetType' | 'targetId'>): string {
  return `${TARGET_TYPE_LABEL[row.targetType] ?? row.targetType} #${row.targetId}`
}

/** 终态单：`approved / rejected / withdrawn` 都不能再处置（docs/50 §6.2 幂等保护 → 46010） */
export function isTerminalCase(row: Pick<ModerationCaseRow, 'status'>): boolean {
  return row.status === 'approved' || row.status === 'rejected' || row.status === 'withdrawn'
}

/**
 * `GET /moderation/cases/{id}` 的 Java 实现返回 `{case, targetExists, targetStatus, snapshot, history}`，
 * 而 `consoleApi.getCase` 的返回类型写的是 `ModerationCaseRow`（缺口）。两种形态都兜。
 */
export function pickCase(payload: unknown): ModerationCaseRow | null {
  if (!payload || typeof payload !== 'object') return null
  const wrapped = (payload as { case?: ModerationCaseRow }).case
  if (wrapped && typeof wrapped.id === 'number') return wrapped
  const direct = payload as ModerationCaseRow
  return typeof direct.id === 'number' ? direct : null
}

// ── 错误呈现（docs/50 §10.4） ──────────────────────────────────────────────

export interface ConsoleFailure {
  message: string
  code: number | null
  /** 46002 时服务端回传的所需权限码 */
  required: string | null
  /** 46015 时服务端回传的既有审核单 id */
  caseId: number | null
}

export function describeFailure(err: unknown): ConsoleFailure {
  if (!(err instanceof ApiError)) {
    return {
      message: err instanceof Error ? err.message || '操作失败' : String(err),
      code: null,
      required: null,
      caseId: null,
    }
  }
  const data = (err.data ?? {}) as { required?: unknown; caseId?: unknown }
  return {
    message: err.message || '操作失败',
    code: err.code,
    required: typeof data.required === 'string' ? data.required : null,
    caseId: typeof data.caseId === 'number' ? data.caseId : null,
  }
}

/**
 * 失败提示行：永远先给 `err.message`；46002 明说缺哪个权限码（`data.required`）。
 * 46010 / 46015 这两个**预期内**的并发结果不在这里处理——它们各自有专门的跳转/刷新动作。
 */
export function failureLines(f: ConsoleFailure): string[] {
  const lines = [f.message]
  if (f.code === ERR.PERMISSION_DENIED) {
    lines.push(f.required ? `缺少权限码：${f.required}` : '权限不足（服务端未回传所需权限码）')
  }
  if (f.code === ERR.TARGET_MISSING) {
    lines.push('目标内容已不存在（可能已被物理清理），无法对该单做出处置。')
  }
  return lines
}

// ── 审计视角（ActionsView 用） ─────────────────────────────────────────────

/** 审核域动作码。服务端只有 `action = :action` 精确匹配，没有前缀查询（见 ActionsView 的扫描说明） */
export const MODERATION_ACTION_LABEL: Record<string, string> = {
  'moderation.decide': '审核决定',
  'moderation.case.assign': '认领 / 指派',
  'moderation.case.create': '建单',
  'moderation.report.handle': '举报处理',
}

export const MODERATION_ACTION_OPTIONS = Object.entries(MODERATION_ACTION_LABEL).map(
  ([value, label]) => ({ label: `${label}（${value}）`, value }),
)

export const AUDIT_RESULT_OPTIONS = [
  { label: '成功', value: 'ok' },
  { label: '被拒', value: 'denied' },
  { label: '失败', value: 'failed' },
]

export function auditDetail(row: AuditLogRow): Record<string, unknown> {
  return row.detail ?? {}
}

/** 决定列：`detail.decision`（Java `AuditFieldAllowlist` 允许写入） */
export function auditDecisionText(row: AuditLogRow): string {
  const decision = auditDetail(row).decision
  if (typeof decision !== 'string') return '—'
  return decisionMeta(decision)?.label ?? decision
}

/** 备注列：`detail.note`（就是作者会看到的 `decision_note`） */
export function auditNoteText(row: AuditLogRow): string {
  const note = auditDetail(row).note
  return typeof note === 'string' && note ? note : '—'
}

/** 展开行的 JSON 文本（用文本插值渲染，绝不 v-html；docs/50 §11.4） */
export function prettyJson(value: unknown): string {
  if (value === null || value === undefined) return '（本条审计没有 detail）'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
