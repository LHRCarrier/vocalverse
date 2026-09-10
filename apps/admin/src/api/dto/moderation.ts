/** 审核域 DTO（docs/50 §6.2 / §10.2）。状态机由服务端强制，前端只做展示与可达性。 */

// ── 审核 ─────────────────────────────────────────────────────────────────

export type ModerationTargetType = 'post' | 'comment' | 'media' | 'direct_message'
export type ModerationStatus = 'pending' | 'approved' | 'rejected' | 'escalated' | 'withdrawn'

/**
 * 审核单的结构化上下文（`moderation_cases.snapshot` jsonb）。
 *
 * ⚠️ **形状随来源变化**：`source='auto'` 是引擎给的、`'report'` 是举报聚合出来的、
 * `'manual'` 是审核员手填的。因此这里只声明**已知会读**的键，其余走索引签名。
 * **不要把它当成稳定契约**——真正稳定的字段在上面一层（targetType/targetId/status）。
 */
export interface ModerationSnapshot {
  authorId?: number
  authorHandle?: string | null
  domain?: string | null
  kind?: string | null
  mediaPublicIds?: string[]
  postId?: number | null
  /** 举报数**只有**在 snapshot 里有（`CaseView` 没有顶层 reportCount） */
  reportCount?: number
  [key: string]: unknown
}

/**
 * 审核单行 —— **与 Java `ModerationController.CaseView` 逐字对齐**。
 *
 * ⚠️ 修正记录（2026-09-10）：v1 写成 `reportCount: number` + `assignee: {id,displayName}` +
 * `decidedBy: {id,displayName}` —— **后端不返回这些**：认领人/决定人只给**标量 id**
 * （`assigneeId` / `decidedBy`），举报数只在 `snapshot.reportCount`。
 * 前端曾用 `as unknown as` 兜底两种形态，那是掩盖而非修复；现在只按真实形态读。
 * 显示"是谁"需要姓名 → 由**管理员列表**在前端 join（`system/AdminsView` 已有数据源），不编造名字。
 */
export interface ModerationCaseRow {
  id: number
  targetType: ModerationTargetType
  targetId: number
  source: 'auto' | 'report' | 'manual'
  reasonCode: string
  priority: number
  status: ModerationStatus
  snippet: string | null
  snapshot: ModerationSnapshot | null
  reporterUserId: number | null
  assigneeId: number | null
  decidedBy: number | null
  decidedAt: string | null
  decisionNote: string | null
  createdAt: string
  updatedAt: string
}

/** 举报行 —— 与 Java `ModerationController.ReportView` 逐字对齐（注意 `handledBy` 存在） */
export interface ModerationReportRow {
  id: number
  reporterUserId: number
  targetType: ModerationTargetType
  targetId: number
  reasonCode: string
  detail: string | null
  status: 'pending' | 'accepted' | 'rejected' | 'duplicate'
  caseId: number | null
  handledBy: number | null
  handledAt: string | null
  createdAt: string
}

/**
 * 审核统计（`GET /moderation/stats`）。
 *
 * ⚠️ `trend` / `decisions` / `approvedToday` / `rejectedToday` 在 v1 里是**前端假设**，
 * Java 的 `ModerationService.stats()` 一度只返回扁平计数 —— 已回派实现方补齐
 * （docs/51 §7.2 I-3）。为避免"后端没给就渲染空白"，**四个字段都标为可选**，
 * 页面缺失时明确显示"后端未提供"而不是画一张空图（`ModerationPanel.vue` 按此处理）。
 */
export interface ModerationStats {
  pending: number
  escalated: number
  /** 可选：后端若未提供，UI 显示「—」并给出原因，而不是显示 0（0 是错误信息） */
  approvedToday?: number
  rejectedToday?: number
  trend?: { date: string; pending: number; approved: number; rejected: number }[]
  decisions?: { decision: string; count: number }[]
  /** 其余后端可能返回的扁平计数（total / withdrawn / reportsPending / byStatus…） */
  [key: string]: unknown
}

export type ModerationDecision = 'approve' | 'hide' | 'delete' | 'reject' | 'escalate'
