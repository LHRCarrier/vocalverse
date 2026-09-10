import { consoleHttp } from './client'
import type {
  AdminRoleRow,
  AdminSessionRow,
  AdminUserRow,
  AuditLogRow,
  AuditResult,
  ConsoleProfile,
  ConsoleSession,
  LrcLineRow,
  LrcUpsert,
  MaterialDetail,
  MaterialRow,
  MaterialUpsert,
  ModerationCaseRow,
  ModerationDecision,
  ModerationReportRow,
  ModerationStats,
  ModerationTargetType,
  PageView,
  PermissionGroup,
  PermissionItem,
  PublishDomain,
  PublishEventRow,
  PublishResult,
  PublishStatus,
  PublishTargetType,
  QuestionDetail,
  QuestionPatch,
  QuestionRow,
  QuestionUpsert,
  ScenarioDetail,
  ScenarioRow,
  ScenarioUpsert,
  SongDetail,
  SongRow,
  SongUpsert,
  TicketRow,
  TicketStatus,
} from './types'

/**
 * Java 侧控制台端点（docs/50 §10.2）。
 * 路径一律 `/api/v1/console/**`；`consoleHttp` 的 base 已含网关前缀（`/manage`）。
 *
 * ⚠️ 每个方法的**路径 / 方法 / 请求体字段名 / query 参数名**都逐字对齐 Java 源
 * （`console/auth`、`console/rbac`、`console/audit`、`console/content`、`console/moderation`）。
 * 2026-09-10 修正的错误（v1 按设计文档想象的部分）：
 * - `PATCH /auth/me`、`POST /auth/password`：**后端不存在这两个端点**（`ConsoleAuthController`
 *   只有 login/refresh/logout/me），原先的 `updateProfile` / `changePassword` 已删除；
 * - 口令重置体是 `{password}` 而不是 `{newPassword}`（`ConsoleRbacController.PasswordReset`）；
 * - 会话列表是 `GET /admins/sessions`（全局分页），**不是** `GET /admins/{id}/sessions`；
 * - 内容列表多传了一个后端不接收的 `q`（四个 `listXxx` 都没有该参数），已去掉；
 * - 上架流水按 `targetType`（`song|listening_material|scenario|book|chapter`）而不是 `domain` 过滤；
 * - 审计多了个后端不接收的 `adminUserId` 之外的想象参数；`actionPrefix` 才是前缀查询的正式参数。
 */
const P = '/api/v1/console'

export interface AdminListQuery extends Record<string, unknown> {
  page?: number
  page_size?: number
  q?: string
  roleId?: number
  status?: string
}

export interface AuditLogQuery extends Record<string, unknown> {
  page?: number
  page_size?: number
  /** 精确匹配（与前缀互斥且优先，`AdminAuditLogRepository.search` 注释） */
  action?: string
  /** 前缀匹配 `action like :actionPrefix || '%'`，控制台「全部审核动作」档用它 */
  actionPrefix?: string
  targetType?: string
  adminUserId?: number
  result?: string
  from?: string
  to?: string
}

/** `GET /admins/sessions` 单页大小上限 100（`@Max(100)`）；会话抽屉的自动翻页用它 */
const SESSION_SCAN_PAGE_SIZE = 100
/** 会话抽屉最多扫这么多页：再多人也不至于让抽屉打上百次请求（够不到时会明示） */
const SESSION_SCAN_MAX_PAGES = 30

/**
 * 某个管理员的在线会话。
 *
 * ⚠️ 后端**只提供全局会话列表**（`GET /admins/sessions` 的参数只有 page/page_size，
 * 没有 `adminUserId` 过滤），所以这里在客户端按 `adminUserId` 过滤。
 * 只扫**在线**会话（服务端 `findActive(now)` 已按未吊销 + 未过期过滤），总量有限。
 * 返回第二个值 = 是否扫到了末尾：false 表示"可能还有会话没被列出"，抽屉必须如实说明。
 */
export async function fetchAdminSessions(
  adminUserId: number,
): Promise<{ items: AdminSessionRow[]; complete: boolean }> {
  const mine: AdminSessionRow[] = []
  for (let page = 1; page <= SESSION_SCAN_MAX_PAGES; page += 1) {
    const res = await consoleHttp.get<PageView<AdminSessionRow>>(`${P}/admins/sessions`, {
      query: { page, page_size: SESSION_SCAN_PAGE_SIZE },
    })
    mine.push(...res.items.filter((row) => row.adminUserId === adminUserId))
    const lastPage = Math.max(1, Math.ceil(res.total / SESSION_SCAN_PAGE_SIZE))
    if (page >= lastPage) return { items: mine, complete: true }
  }
  return { items: mine, complete: false }
}

/**
 * 权限目录：后端按 module 分组返回 `{module, permissions[]}`，
 * 前端统一成 `{module, items[]}`（naive-ui 的矩阵按 `items` 渲染）。
 */
async function fetchPermissionGroups(): Promise<PermissionGroup[]> {
  const raw = await consoleHttp.get<{ module: string; permissions: PermissionItem[] }[]>(
    `${P}/permissions`,
  )
  return raw.map((group) => ({ module: group.module, items: group.permissions }))
}

export const consoleApi = {
  // ── 身份 ────────────────────────────────────────────────────────────────
  /** 登录：`POST /auth/login`，响应是平铺的 `SessionView`（token + 主体摘要） */
  login: (username: string, password: string) =>
    consoleHttp.post<ConsoleSession>(`${P}/auth/login`, { username, password }, { anonymous: true }),

  logout: () => consoleHttp.post<{ revoked: boolean }>(`${P}/auth/logout`),

  /** 档案：`MeView`（adminUserId / roleCode / roleName / permissions / sessionId） */
  me: () => consoleHttp.get<ConsoleProfile>(`${P}/auth/me`),

  // ── 管理员账号 ──────────────────────────────────────────────────────────
  listAdmins: (query: AdminListQuery) =>
    consoleHttp.get<PageView<AdminUserRow>>(`${P}/admins`, { query }),

  createAdmin: (body: { username: string; displayName: string; password: string; roleId: number }) =>
    consoleHttp.post<AdminUserRow>(`${P}/admins`, body),

  updateAdmin: (
    id: number,
    body: { displayName?: string; roleId?: number; status?: 'active' | 'disabled' },
  ) => consoleHttp.patch<AdminUserRow>(`${P}/admins/${id}`, body),

  /** 重置口令：字段名是 `password`（`ConsoleRbacController.PasswordReset`），不是 `newPassword` */
  resetAdminPassword: (id: number, body: { password: string }) =>
    consoleHttp.post<{ reset: boolean; adminUserId: number; self: boolean }>(
      `${P}/admins/${id}/password`,
      body,
    ),

  /** 某账号的在线会话（全局端点的客户端过滤版，见 `fetchAdminSessions`） */
  listAdminSessions: fetchAdminSessions,

  revokeAdminSessions: (id: number) =>
    consoleHttp.del<{ revoked: boolean; adminUserId: number }>(`${P}/admins/${id}/sessions`),

  // ── 角色与权限 ──────────────────────────────────────────────────────────
  listRoles: () => consoleHttp.get<AdminRoleRow[]>(`${P}/roles`),

  createRole: (body: {
    code: string
    name: string
    description?: string
    rank?: number
    permissionCodes?: string[]
  }) => consoleHttp.post<AdminRoleRow>(`${P}/roles`, body),

  /** `RolePatch` 允许改 code/name/description/rank/permissionCodes（内置角色的 code 由服务端守门） */
  updateRole: (
    id: number,
    body: { code?: string; name?: string; description?: string; rank?: number; permissionCodes?: string[] },
  ) => consoleHttp.patch<AdminRoleRow>(`${P}/roles/${id}`, body),

  deleteRole: (id: number) =>
    consoleHttp.del<{ deleted: boolean; roleId: number }>(`${P}/roles/${id}`),

  listPermissions: fetchPermissionGroups,

  setRolePermissions: (id: number, permissionCodes: string[]) =>
    consoleHttp.put<AdminRoleRow>(`${P}/roles/${id}/permissions`, { permissionCodes }),

  // ── 审计 ────────────────────────────────────────────────────────────────
  listAuditLogs: (query: AuditLogQuery) =>
    consoleHttp.get<PageView<AuditLogRow>>(`${P}/audit-logs`, { query }),

  // ── 审核 ────────────────────────────────────────────────────────────────
  listCases: (query: {
    page?: number
    page_size?: number
    status?: string
    targetType?: ModerationTargetType
    priority?: number
    assigneeId?: number
  }) => consoleHttp.get<PageView<ModerationCaseRow>>(`${P}/moderation/cases`, { query }),

  getCase: (id: number) => consoleHttp.get<ModerationCaseRow>(`${P}/moderation/cases/${id}`),

  createCase: (body: {
    targetType: ModerationTargetType
    targetId: number
    reasonCode: string
    priority?: number
    note?: string
  }) => consoleHttp.post<ModerationCaseRow>(`${P}/moderation/cases`, body),

  assignCase: (id: number, assigneeId: number | null) =>
    consoleHttp.post<ModerationCaseRow>(`${P}/moderation/cases/${id}/assign`, { assigneeId }),

  decideCase: (id: number, body: { decision: ModerationDecision; reasonCode: string; note?: string }) =>
    consoleHttp.post<ModerationCaseRow>(`${P}/moderation/cases/${id}/decision`, body),

  listReports: (query: {
    page?: number
    page_size?: number
    status?: string
    targetType?: ModerationTargetType
  }) => consoleHttp.get<PageView<ModerationReportRow>>(`${P}/moderation/reports`, { query }),

  handleReport: (
    id: number,
    body: { decision: 'accept' | 'reject' | 'duplicate'; note?: string },
  ) => consoleHttp.post<ModerationReportRow>(`${P}/moderation/reports/${id}/handle`, body),

  moderationStats: (days = 30) =>
    consoleHttp.get<ModerationStats>(`${P}/moderation/stats`, { query: { days } }),

  // ── 运营：内容上下架 ────────────────────────────────────────────────────
  /** 歌曲：`GET /content/songs?page&page_size&status`（**没有** q 关键词参数） */
  listSongs: (query: { page?: number; page_size?: number; status?: string }) =>
    consoleHttp.get<PageView<SongRow>>(`${P}/content/songs`, { query }),

  /** 听力素材：`GET /content/listening-materials?page&page_size&status` */
  listMaterials: (query: { page?: number; page_size?: number; status?: string }) =>
    consoleHttp.get<PageView<MaterialRow>>(`${P}/content/listening-materials`, { query }),

  /** 场景：`GET /content/scenarios?page&page_size&status&sceneType`（多一个 sceneType 过滤） */
  listScenarios: (query: { page?: number; page_size?: number; status?: string; sceneType?: string }) =>
    consoleHttp.get<PageView<ScenarioRow>>(`${P}/content/scenarios`, { query }),

  /** 题库：`GET /content/questions?page&page_size&examRevision&status`，只读（无 publish） */
  listQuestions: (query: {
    page?: number
    page_size?: number
    examRevision?: number
    status?: string
  }) => consoleHttp.get<PageView<QuestionRow>>(`${P}/content/questions`, { query }),

  /** 上下架：路径域是 `song|listening|scenario`（`@PathVariable` 拼出来的端点路径用复数） */
  publish: (domain: PublishDomain, id: number, status: PublishStatus) =>
    consoleHttp.post<PublishResult>(`${P}/content/${domainPath(domain)}/${id}/publish`, { status }),

  publishEvents: (query: { page?: number; page_size?: number; targetType?: PublishTargetType }) =>
    consoleHttp.get<PageView<PublishEventRow>>(`${P}/content/publish-events`, {
      query: { page: query.page, page_size: query.page_size, targetType: query.targetType },
    }),

  listTickets: (query: { page?: number; page_size?: number; status?: string; kind?: string }) =>
    consoleHttp.get<PageView<TicketRow>>(`${P}/content/tickets`, { query }),

  /**
   * 工单处置：状态流转 + 管理员回复。
   *
   * ⚠️ 必须同时支持 `adminReply`：旧管理端的 `AdminTicketController.TicketPatch` 就带回复字段，
   * 而旧面已随本 PR 退役 → 控制台是**唯一**工单面，只做状态流转会**丢掉"回复用户"这个能力**（功能回退）。
   * 状态机由服务端 `TicketWorkflowService` 强制前向流转（禁回退、closed 终态），
   * 非法流转返回 40001；前端不做本地状态机（避免两套规则）。
   */
  updateTicket: (id: number, body: { status?: TicketStatus; adminReply?: string }) =>
    consoleHttp.patch<TicketRow>(`${P}/content/tickets/${id}`, body),

  /** 单条工单详情（用户正文可能很长，列表页不展开） */
  getTicket: (id: number) => consoleHttp.get<TicketRow>(`${P}/content/tickets/${id}`),

  // ── 运营：内容增改删（docs/50 §15.2 G-17 的写路径） ──────────────────────
  //
  // 权威：`console/content/ConsoleContentWriteController`（`@RequestMapping("/api/v1/console/content")`）。
  // 三条与读写列表**不同**的口径，写错任何一条都会静默改错数据：
  // 1. 更新用 **PUT + 全量体**（不是 PATCH）：`SongUpsert` 等是完整 record，缺字段服务端按默认值覆盖；
  // 2. 编辑前必须 `getXxx(id)` 回读：列表行只有 6 个字段，缺 `durationS`/`bpm`/`transcript` 等；
  // 3. `DELETE` = **归档**（`status → archived`），不是物理删除（§6.1 拍板）。

  getSong: (id: number) => consoleHttp.get<SongDetail>(`${P}/content/songs/${id}`),

  createSong: (body: SongUpsert) => consoleHttp.post<SongDetail>(`${P}/content/songs`, body),

  /** 更新歌曲（`PUT /songs/{id}`）：**全量**替换，未填字段会被服务端默认值覆盖 */
  updateSong: (id: number, body: SongUpsert) =>
    consoleHttp.put<SongDetail>(`${P}/content/songs/${id}`, body),

  /** 归档歌曲（软删）：`status → archived`，行与审计都保留 */
  archiveSong: (id: number) => consoleHttp.del<SongDetail>(`${P}/content/songs/${id}`),

  /** 歌曲 LRC（读）：返回按 `seq` 升序的整首歌词 */
  getSongLrc: (id: number) => consoleHttp.get<LrcLineRow[]>(`${P}/content/songs/${id}/lrc`),

  /**
   * 歌曲 LRC（整首重写）：服务端「删旧插新 + seq 重排」。
   *
   * ⚠️ 若该曲 `pitchRefStatus` 原为 `ready`，服务端会置回 `missing` 触发 Python 离线重提取
   * （`replaceLrc` 注释：LRC 改了而参考旋律还是旧的，跟唱分会给出"看似有据的错分"）——
   * 所以调用方必须把这件事告诉运营，不能看起来"只改了个歌词"。
   */
  replaceSongLrc: (id: number, body: LrcUpsert) =>
    consoleHttp.put<LrcLineRow[]>(`${P}/content/songs/${id}/lrc`, body),

  getMaterial: (id: number) =>
    consoleHttp.get<MaterialDetail>(`${P}/content/listening-materials/${id}`),

  createMaterial: (body: MaterialUpsert) =>
    consoleHttp.post<MaterialDetail>(`${P}/content/listening-materials`, body),

  updateMaterial: (id: number, body: MaterialUpsert) =>
    consoleHttp.put<MaterialDetail>(`${P}/content/listening-materials/${id}`, body),

  archiveMaterial: (id: number) =>
    consoleHttp.del<MaterialDetail>(`${P}/content/listening-materials/${id}`),

  getScenario: (id: number) => consoleHttp.get<ScenarioDetail>(`${P}/content/scenarios/${id}`),

  createScenario: (body: ScenarioUpsert) =>
    consoleHttp.post<ScenarioDetail>(`${P}/content/scenarios`, body),

  updateScenario: (id: number, body: ScenarioUpsert) =>
    consoleHttp.put<ScenarioDetail>(`${P}/content/scenarios/${id}`, body),

  archiveScenario: (id: number) => consoleHttp.del<ScenarioDetail>(`${P}/content/scenarios/${id}`),

  getQuestion: (id: number) => consoleHttp.get<QuestionDetail>(`${P}/content/questions/${id}`),

  /** 新建题目：同版本内 `itemIndex` 撞车被服务端以 46007 拒绝（`createQuestion` 显式查重） */
  createQuestion: (body: QuestionUpsert) =>
    consoleHttp.post<QuestionDetail>(`${P}/content/questions`, body),

  /** 更新题目：只能改题干 / 参考答案 / 状态，身份字段（版本、序号）不可改 */
  updateQuestion: (id: number, body: QuestionPatch) =>
    consoleHttp.put<QuestionDetail>(`${P}/content/questions/${id}`, body),

  archiveQuestion: (id: number) => consoleHttp.del<QuestionDetail>(`${P}/content/questions/${id}`),
}

/**
 * 上下架的内容域 code → 端点路径段（`ConsoleContentController` 的 `@GetMapping` 路径）。
 *
 * 为什么不让调用方直接写路径段：`PublishService` 用的域 code 是**单数**（`song`/`listening`），
 * 而端点路径是**复数**（`songs`/`listening-materials`）—— 两套词混在一处极易写错，
 * 这里一次性把映射钉死（`audit` 里的 `targetTypeOf` 也演示了单数 code 的用法）。
 */
function domainPath(domain: PublishDomain): string {
  switch (domain) {
    case 'song':
      return 'songs'
    case 'listening':
      return 'listening-materials'
    case 'scenario':
      return 'scenarios'
  }
}

/**
 * 上架流水行的 `detail`（JSON 文本）→ 前后状态。
 *
 * 后端把 `prevStatus`/`nextStatus` 写进审计 detail（`ConsoleContentController.applyPublish`），
 * 而 `publish-events` 只回传 `detail` 原文，所以这里解析一次；解析不出来就如实返回 null
 * （页面显示「—」，不猜）。
 */
export function publishEventDetail(row: PublishEventRow): {
  prevStatus: string | null
  nextStatus: string | null
} {
  const empty = { prevStatus: null, nextStatus: null }
  if (!row.detail) return empty
  try {
    const parsed: unknown = JSON.parse(row.detail)
    if (typeof parsed !== 'object' || parsed === null) return empty
    const record = parsed as Record<string, unknown>
    return {
      prevStatus: typeof record.prevStatus === 'string' ? record.prevStatus : null,
      nextStatus: typeof record.nextStatus === 'string' ? record.nextStatus : null,
    }
  } catch {
    return empty
  }
}

/**
 * 上架流水的「内容域」：后端**不返回** domain，只给 `action`（`content.{domain}.publish`，
 * 见 `ConsoleContentController.applyPublish`），故从前缀推导；推不出来时返回 null，
 * 页面回落到 `targetType` 而不是编一个域出来。
 */
export function publishEventDomain(row: PublishEventRow): string | null {
  const parts = row.action.split('.')
  return parts.length === 3 && parts[0] === 'content' && parts[2] === 'publish' ? parts[1] : null
}

/** 审计结果取值域（`AuditService` 只写这三个；用于下拉选项与类型收敛） */
export const AUDIT_RESULTS: AuditResult[] = ['ok', 'denied', 'failed']
