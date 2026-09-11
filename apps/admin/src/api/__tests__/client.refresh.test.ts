// @vitest-environment happy-dom
/**
 * 控制台令牌续期的契约回归（2026-09-11 实测缺陷）。
 *
 * **缺陷**：`client.ts` 的 `refreshOnce()` 按**平铺**读续期响应（`data.accessToken`），
 * 而后端 `POST /auth/refresh` 回的是 `ConsoleAuthController.SessionView` —— 令牌
 * **嵌在 `data.token` 下**（`{token:{…}, adminUserId, …}`），与登录响应同形。
 * 于是 `saveTokens(body.data)` 两个字段都取到 `undefined`，
 * `localStorage.setItem(k, undefined)` 把令牌**写成字符串 `"undefined"`**：
 *   - 下一次续期发 `refreshToken:"undefined"` → Java 回 **46001「刷新令牌无效」**；
 *   - 所有业务请求带 `Authorization: Bearer undefined` → **整站 401**。
 *
 * **触发路径**（必然复现，不依赖时序）：登录 → 任一请求 401（access token 15min 过期，
 * 或 Python 侧控制台端点因密钥未配置 fail-closed）→ 续期 → 令牌被写坏 → 之后全站 401。
 * 实测证据：Java 日志 `code=46001 刷新令牌无效` 恰好出现在每次成功轮换后 ~118ms；
 * `admin_sessions` 中 5→6 / 7→8 / 9→10 三轮轮换各紧跟一次该失败。
 *
 * 本文件钉住两件事，**修复前两条都会失败**：
 *   ① 续期后 localStorage 里必须是真令牌（不是 `"undefined"`），且重试请求带新令牌；
 *   ② 续期成功后仍然 401 时**只续期一次** —— 若不与 ① 同时收紧，会退化成
 *      「续期永远成功、401 永远不消失」的无限续期循环（每轮烧掉一条会话轮换）。
 *      修复前本用例不是断言失败，而是**无限递归直到 Node 堆耗尽**：实测把 `client.ts`
 *      回退到修复前跑本文件，vitest 进程以
 *      `FATAL ERROR: Ineffective mark-compacts near heap limit - JavaScript heap out of memory`
 *      崩溃。这正是无限续期循环的实证，也说明该守卫必须与 ① 同批落地。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { consoleHttp, clearTokens, ERR, saveTokens } from '@/api'

/** 与控制台 `client.ts` 的存储键一致（顺带钉住键名：换 key 会让既有登录态静默丢失） */
const ACCESS_KEY = 'vv_console_token'
const REFRESH_KEY = 'vv_console_refresh'
/** dev 档 consoleBase = '/manage'（`import.meta.env.PROD` 为假） */
const REFRESH_URL = '/manage/api/v1/console/auth/refresh'

/**
 * `POST /auth/refresh` 的**真实**响应形状（逐字照抄 `ConsoleAuthController.SessionView`
 * + `TokenResponse`）—— 令牌在 `data.token` 下，不在 `data` 下。
 */
function sessionEnvelope(accessToken: string, refreshToken: string) {
  return {
    code: ERR.OK,
    message: 'ok',
    data: {
      token: { accessToken, refreshToken, tokenType: 'Bearer', expiresIn: 900 },
      adminUserId: 1,
      username: 'admin',
      displayName: 'admin',
      roleCode: 'super',
      permissions: ['ops:metric:read'],
    },
  }
}

/** `request()` 只用到 status / ok / headers.get / json，不依赖真实 Response 实现 */
function jsonResponse(body: unknown, status = 200): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: () => null },
    json: async () => body,
  } as unknown as Response
}

function authHeader(init?: RequestInit): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.Authorization
}

describe('控制台令牌续期（SessionView 形状）', () => {
  beforeEach(() => {
    localStorage.clear()
    clearTokens()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('续期成功后落盘真令牌，重试请求带上新 access token（修复前落盘 "undefined"）', async () => {
    saveTokens({ accessToken: 'expired-access', refreshToken: 'valid-refresh' })

    const seenAuth: string[] = []
    let businessCalls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input) === REFRESH_URL) {
          return jsonResponse(sessionEnvelope('new-access', 'new-refresh'))
        }
        businessCalls += 1
        seenAuth.push(authHeader(init) ?? '')
        if (businessCalls === 1) {
          return jsonResponse(
            { code: ERR.NOT_LOGGED_IN, message: '登录已过期', data: null },
            401,
          )
        }
        return jsonResponse({ code: ERR.OK, message: 'ok', data: { ok: true } })
      }),
    )

    await expect(consoleHttp.get<{ ok: boolean }>('/probe')).resolves.toEqual({ ok: true })

    // ① 真令牌落盘（修复前这里是字符串 "undefined"）
    expect(localStorage.getItem(ACCESS_KEY)).toBe('new-access')
    expect(localStorage.getItem(REFRESH_KEY)).toBe('new-refresh')
    // ② 重试确实换了新令牌（修复前重试带的是 "Bearer undefined"）
    expect(seenAuth).toEqual(['Bearer expired-access', 'Bearer new-access'])
  })

  it('续期成功后仍 401 → 只续期一次并清空令牌（修复前无限续期）', async () => {
    saveTokens({ accessToken: 'expired-access', refreshToken: 'valid-refresh' })

    let businessCalls = 0
    let refreshCalls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input) === REFRESH_URL) {
          refreshCalls += 1
          return jsonResponse(sessionEnvelope('new-access', 'new-refresh'))
        }
        businessCalls += 1
        // 非令牌原因的 401（Python fail-closed / 权限 / 配置错误都长这样）
        return jsonResponse({ code: ERR.NOT_LOGGED_IN, message: 'unauthorized', data: null }, 401)
      }),
    )

    await expect(consoleHttp.get('/probe')).rejects.toThrow()

    expect(refreshCalls).toBe(1) // 不再续期第二轮（修复前会一直续期下去）
    expect(businessCalls).toBe(2) // 原请求 + 一次重试
    expect(localStorage.getItem(ACCESS_KEY)).toBeNull()
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull()
  })
})
