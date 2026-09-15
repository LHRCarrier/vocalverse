/**
 * 身份与 RBAC DTO（docs/50 §4）。
 *
 * ⚠️ 本文件的字段**逐字对齐 Java 源**，不是按设计文档的想象形状写的。权威来源：
 * - 登录：`console/auth/ConsoleAuthController.SessionView` + `TokenResponse`
 *   （`ConsoleAuthService.LoginResult` 是它的组装来源）；
 * - 档案：`console/auth/ConsoleAuthController.MeView`；
 * - 账号/角色/会话：`console/rbac/ConsoleRbacController.AdminView` / `RoleView` / `SessionView`；
 * - 审计：`console/audit/ConsoleAuditController.AuditLogView`。
 *
 * 2026-09-10 修正记录（v1 的臆造字段 → 后端真实形态）：
 * | 旧字段 | 真实情况 |
 * | --- | --- |
 * | `ConsoleProfile.id` | 真名 `adminUserId`；另有 `roleCode`/`roleName`/`sessionId` |
 * | `ConsoleProfile.role: {id,code,name}` | **后端不返回角色对象**，只有扁平的 `roleCode`/`roleName` |
 * | `ConsoleProfile.lastLoginAt` | **`/auth/me` 不返回**（只有 `AdminView` 有），页面不再显示 |
 * | `TokenPair.profile` | 登录响应的主体摘要是**平铺**的（`adminUserId`/`username`/…），不是嵌套 `profile` |
 * | `AdminUserRow.role: RoleBrief` | 扁平 `roleId`/`roleCode`/`roleName`（可能是 null：roleId 悬空时） |
 * | `AdminUserRow.updatedAt` | **后端不返回**该列 |
 * | `AdminSessionRow.adminUserId` 有、缺 `adminUsername` | 真实有 `adminUsername`（服务端 join 出来的用户名） |
 * | `AdminSessionRow.current` | **后端不返回**「哪个是当前会话」，该列已删除（不再显示假标记） |
 * | `AdminRoleRow.rank: number` | Java 是 `Short`，可能为 null → `number | null` |
 * | `AuditLogRow.result` 宽松 string | 服务端只写 ok/denied/failed（`AuditService`），此处收窄为联合 |
 * | `AuditLogRow.durationMs` | **`AuditLogView` 不返回**（实体有该列但视图没暴露），展开行不再显示"耗时" |
 */

// ── 认证 ──────────────────────────────────────────────────────────────────

/** `ConsoleAuthController.TokenResponse`（tokenType 恒为 "Bearer"、expiresIn 为秒） */
export interface TokenResponse {
  accessToken: string
  refreshToken: string
  tokenType: string
  expiresIn: number
}

/**
 * `ConsoleAuthController.MeView` —— `GET /auth/me` 的 data。
 *
 * `permissions` 以**库为准**重新解析（`ConsoleAuthController.me` 注释）：改权但令牌未过期时，
 * 这里的列表可能比令牌里的快照新，展示应以本字段为准。
 */
export interface ConsoleProfile {
  adminUserId: number
  username: string
  displayName: string
  roleCode: string
  roleName: string
  permissions: string[]
  sessionId: number
}

/**
 * `ConsoleAuthController.SessionView` —— 登录 / 刷新响应的 data。
 *
 * 令牌 + 主体摘要平铺在同一层（前端据此直接渲染侧栏，不必再打一次 `/me`）。
 * 这是 v1 `TokenPair{accessToken,refreshToken,expiresIn,profile}` 的真实形态。
 */
export interface ConsoleSession {
  token: TokenResponse
  adminUserId: number
  username: string
  displayName: string
  roleCode: string
  permissions: string[]
}

// ── 管理员账号 ────────────────────────────────────────────────────────────

/** `ConsoleRbacController.AdminView`（`GET/POST/PATCH /admins`） */
export interface AdminUserRow {
  id: number
  username: string
  displayName: string
  /** `roleId` 在库里是 NOT NULL，但 Java 按 `roles.findById(...).orElse(null)` 取 → 可能为 null */
  roleId: number | null
  roleCode: string | null
  roleName: string | null
  status: 'active' | 'disabled' | string
  failedAttempts: number | null
  lockedUntil: string | null
  tokenEpoch: number | null
  lastLoginAt: string | null
  lastLoginIp: string | null
  createdAt: string
}

/** `ConsoleRbacController.SessionView`（`GET /admins/sessions`） */
export interface AdminSessionRow {
  id: number
  adminUserId: number
  /** 服务端按 `adminUserId` 反查出的账号名（Java 自己 join，不需要前端再查一次） */
  adminUsername: string
  issuedAt: string
  expiresAt: string
  ip: string | null
  userAgent: string | null
}

// ── 角色与权限 ────────────────────────────────────────────────────────────

/** `ConsoleRbacController.RoleView`（`GET/POST/PATCH /roles`、`PUT /roles/{id}/permissions`） */
export interface AdminRoleRow {
  id: number
  code: string
  name: string
  description: string | null
  builtin: boolean
  /** Java `Short`（排序权重），可能为 null */
  rank: number | null
  permissionCodes: string[]
  /** `admin_users.countByRoleId`：仍有成员时删除会被服务端以 46006 拒绝 */
  memberCount: number
}

/** `GET /permissions` 里的一项（`PermissionCatalog.Permission` 的四个对外字段） */
export interface PermissionItem {
  code: string
  name: string
  description: string | null
  /** 组内排序（Java `sort`），目录顺序即后端顺序 */
  sort: number
}

/**
 * `GET /permissions` 的 data 是 `[{module, permissions:[...]}]`（按 module 分组），
 * 与 v1 猜的 `{module, items}` 不同；`consoleApi.listPermissions()` 负责就地改名成 `items`。
 */
export interface PermissionGroup {
  module: string
  items: PermissionItem[]
}

// ── 审计 ──────────────────────────────────────────────────────────────────

/** 审计结果：`AuditService` 只写这三个值 */
export type AuditResult = 'ok' | 'denied' | 'failed'

/**
 * `ConsoleAuditController.AuditLogView`（`GET /audit-logs`）。
 *
 * ⚠️ `detail` 是服务端按字段白名单裁剪后的 JSON（`AuditFieldAllowlist`），
 * 白名单外的键会被静默丢弃 —— "detail 里没有某字段"不等于"这次操作没有该字段"。
 */
export interface AuditLogRow {
  id: number
  adminUserId: number | null
  adminUsername: string
  action: string
  targetType: string | null
  targetId: string | null
  result: AuditResult | string
  errorCode: number | null
  summary: string
  detail: Record<string, unknown> | null
  requestId: string | null
  ip: string | null
  createdAt: string
}
