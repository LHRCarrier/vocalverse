import { ApiError, ERR } from './types'
import type { Envelope } from './types'
import type { ConsoleSession } from './dto/identity'

/**
 * 控制台 HTTP 客户端（docs/50 §3.2 / §10.1）。
 *
 * 两个上游，两个 client 实例：
 *   - `consoleHttp` → Java（默认 `/manage`）—— 身份/RBAC/审计/审核/内容
 *   - `opsHttp`     → Python（默认 `/api/v1`）—— 运维/指标/预警/LLM trace/书籍
 * 之所以不合并成一个"聚合后端"，见 docs/50 §3.2：**每个服务只暴露自己拥有（写）的数据**，
 * 避免 Java 读 Python 的表（破坏单写方矩阵）。
 *
 * 令牌隔离：控制台令牌存 `vv_console_*`，与 App 的 `vv_token` **刻意不互通**
 * （docs/50 §4.1：管理端身份与用户身份解耦，两套身份不能互登）。
 */

const ACCESS_KEY = 'vv_console_token'
const REFRESH_KEY = 'vv_console_refresh'

/**
 * 两个上游的基址。
 *
 * **默认值写在代码里，不依赖 `.env` 文件**——仓库约定 `.env` 不入库（只提交 `.env.example`，
 * 同 apps/web）。若把基址只放在 `.env.development` / `.env.production`，新克隆的仓库
 * 构建出来会打到错误的路径。这里按 `import.meta.env.PROD` 给出正确默认，
 * `.env` 仅用于**覆盖**（见 `apps/admin/.env.example`）。
 */
const DEFAULT_CONSOLE_BASE = import.meta.env.PROD ? '/console/manage' : '/manage'
const DEFAULT_OPS_BASE = import.meta.env.PROD ? '/console/api/v1' : '/api/v1'

export const consoleBase = import.meta.env.VITE_CONSOLE_BASE || DEFAULT_CONSOLE_BASE
export const opsBase = import.meta.env.VITE_OPS_BASE || DEFAULT_OPS_BASE

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

/**
 * 落盘一对令牌。
 *
 * ⚠️ 入参形状：登录/刷新响应的 `token` 是 `ConsoleAuthController.TokenResponse`
 * （`accessToken` / `refreshToken` / `tokenType` / `expiresIn`）；这里只取前两个，
 * 故用结构化参数类型而不是整个 DTO —— v1 引用的 `TokenPair` 在后端**不存在**
 * （它把 token 与 profile 混在一个对象里，真实响应是 `{token:{...}, adminUserId, ...}`）。
 */
export function saveTokens(pair: { accessToken: string; refreshToken: string }): void {
  localStorage.setItem(ACCESS_KEY, pair.accessToken)
  localStorage.setItem(REFRESH_KEY, pair.refreshToken)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

/** 未认证/令牌失效时的统一出口；由路由层注入（避免 client 依赖 router） */
type UnauthorizedHandler = () => void
let onUnauthorized: UnauthorizedHandler = () => {}
export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  onUnauthorized = handler
}

/** 记录最近一次失败的 request id，供错误提示展示（便于对着服务端日志排查） */
let lastRequestId: string | null = null
export function getLastRequestId(): string | null {
  return lastRequestId
}

let refreshing: Promise<boolean> | null = null

/**
 * 单飞刷新：并发 401 只触发一次 refresh，其余请求等同一个 Promise。
 * 刷新失败 → 清空令牌 → 交回调用方抛 46001。
 *
 * ⚠️ 响应形状（2026-09-11 实测缺陷）：`POST /auth/refresh` 的 data 是
 * `ConsoleAuthController.SessionView` —— 令牌**嵌在 `data.token` 下**
 * （`{token:{accessToken,refreshToken,tokenType,expiresIn}, adminUserId, …}`），与登录响应**同形**。
 * 此前这里按平铺读写（`body.data.accessToken`），于是 `saveTokens(body.data)` 取到两个 undefined，
 * `localStorage.setItem(k, undefined)` 把令牌**存成字符串 "undefined"** → 下一次刷新发
 * `refreshToken:"undefined"` → Java 回 46001「刷新令牌无效」→ 令牌清空、整站 401。
 * 触发路径：登录后等 access token 过期（15min），或任意 401 引发续期 —— 必然复现。
 * 登录路径（`stores/auth.ts` 写 `saveTokens(session.token)`）一直是对的，
 * 两条路径对同一响应形状的口径必须一致。
 */
async function refreshOnce(): Promise<boolean> {
  if (refreshing) return refreshing
  const refreshToken = localStorage.getItem(REFRESH_KEY)
  if (!refreshToken) return false
  refreshing = (async () => {
    try {
      const res = await fetch(`${consoleBase}/api/v1/console/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refreshToken }),
      })
      const body = (await res.json()) as Envelope<ConsoleSession>
      if (body.code !== ERR.OK || !body.data?.token) return false
      saveTokens(body.data.token)
      return true
    } catch {
      return false
    } finally {
      refreshing = null
    }
  })()
  return refreshing
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  /** query 参数；undefined/null/'' 自动丢弃 */
  query?: Record<string, unknown>
  body?: unknown
  /** 跳过 Authorization（登录/刷新用） */
  anonymous?: boolean
  /** 401 时不尝试 refresh（refresh 自身调用用） */
  noRefresh?: boolean
  signal?: AbortSignal
}

function buildUrl(base: string, path: string, query?: Record<string, unknown>): string {
  const url = `${base}${path}`
  if (!query) return url
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) v.forEach((item) => sp.append(k, String(item)))
    else sp.append(k, String(v))
  }
  const qs = sp.toString()
  return qs ? `${url}?${qs}` : url
}

async function request<T>(base: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (!opts.anonymous) {
    const token = getAccessToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }

  let res: Response
  try {
    res = await fetch(buildUrl(base, path, opts.query), {
      method: opts.method ?? 'GET',
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      signal: opts.signal,
    })
  } catch (err) {
    // 网络层失败（断网/服务未起）——给出可操作提示，而不是空 message
    throw new ApiError(-1, `网络请求失败：${(err as Error).message}`, null)
  }

  lastRequestId = res.headers.get('X-Request-Id')

  if (res.status === 401 && !opts.anonymous && !opts.noRefresh) {
    const ok = await refreshOnce()
    // 重试**只重试一次**（noRefresh=true）：续期成功后仍然 401，说明问题不在令牌
    // （Python 侧 fail-closed、token_epoch 被吊销、权限/配置错误都会 401）。
    // 若这里放开（此前是 noRefresh:false），每次重试都会再续期一轮 —— 续期永远成功、
    // 401 永远不消失，就是一个无限续期循环（每轮烧掉一条 admin_sessions 轮换）。
    // 此前它没暴露，只是因为续期把令牌写坏成 "undefined" 后下一轮必然失败，属于
    // **偶然的刹车**；修好令牌写入后必须显式保留这个刹车。
    if (ok) return request<T>(base, path, { ...opts, noRefresh: true })
    clearTokens()
    onUnauthorized()
    throw new ApiError(ERR.NOT_LOGGED_IN, '登录已过期，请重新登录', null)
  }

  let body: Envelope<T> | null = null
  try {
    body = (await res.json()) as Envelope<T>
  } catch {
    body = null
  }

  if (!body || typeof body.code !== 'number') {
    // 非 Envelope 响应：Spring 安全层的 401/403 默认错误体走这条（docs/50 §3 已知形态差异）
    throw new ApiError(
      res.ok ? -2 : res.status,
      `服务返回非标准响应（HTTP ${res.status}）`,
      null,
    )
  }

  if (body.code !== ERR.OK) {
    if (body.code === ERR.NOT_LOGGED_IN) {
      clearTokens()
      onUnauthorized()
    }
    throw new ApiError(body.code, body.message || '请求失败', body.data)
  }

  return body.data as T
}

function makeClient(base: string) {
  return {
    get: <T>(path: string, opts?: RequestOptions) => request<T>(base, path, { ...opts, method: 'GET' }),
    post: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
      request<T>(base, path, { ...opts, method: 'POST', body }),
    patch: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
      request<T>(base, path, { ...opts, method: 'PATCH', body }),
    put: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
      request<T>(base, path, { ...opts, method: 'PUT', body }),
    del: <T>(path: string, opts?: RequestOptions) =>
      request<T>(base, path, { ...opts, method: 'DELETE' }),
  }
}

/** Java 控制台域 */
export const consoleHttp = makeClient(consoleBase)
/** Python 运维域 */
export const opsHttp = makeClient(opsBase)

export { request as rawRequest }
