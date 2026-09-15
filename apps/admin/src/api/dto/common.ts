/**
 * 契约基元：envelope / 分页 / 错误码 / 业务异常（docs/50 §10.1、docs/api/envelope.md）。
 *
 * 从 `api/types.ts` 拆出（该文件超 `max-lines` 350 上限）——本文件不含任何业务 DTO，
 * 因此可以被 `client.ts` 单独依赖，不必拖着整个控制台的类型面。
 */

/**
 * 控制台 DTO 与契约常量（docs/50 §10）。
 *
 * ⚠️ 隔离说明：这里**不复用** `apps/web/src/api/generated/*`（那是 App 的契约生成物），
 * 控制台用自己的手写 DTO。理由见 docs/50 §3.1——两端契约独立演进，
 * 共享生成物会让控制台被 App 的契约变更绑住。
 */

/** 统一 envelope（docs/api/envelope.md）：成功 code=0，错误 data 恒 null */
export interface Envelope<T> {
  code: number
  message: string
  data: T | null
}

/** 分页体（Java PageView，page 从 1 起） */
export interface PageView<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/** 控制台错误码（docs/50 §10.4 · 需先登记 docs/api/error-codes.md） */
export const ERR = {
  OK: 0,
  NOT_LOGGED_IN: 46001,
  PERMISSION_DENIED: 46002,
  ACCOUNT_DISABLED: 46003,
  ADMIN_NOT_FOUND: 46004,
  USERNAME_TAKEN: 46005,
  ROLE_IN_USE: 46006,
  BAD_PARAM: 46007,
  LOGIN_THROTTLED: 46008,
  TARGET_MISSING: 46009,
  CASE_STATE_CONFLICT: 46010,
  PUBLISH_VALIDATION_FAILED: 46011,
  TRACE_NOT_FOUND: 46012,
  TELEMETRY_UNAVAILABLE: 46013,
  OPS_CHANNEL_DISABLED: 46014,
  REPORT_ALREADY_PENDING: 46015,
} as const

/** 业务错误：带上 code 与后端附带的 data（如 required / violations / retryAfter） */
export class ApiError extends Error {
  readonly code: number
  readonly data: unknown

  constructor(code: number, message: string, data: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.data = data
  }
}
