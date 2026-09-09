/**
 * 认证 store（docs/18 §3-J1）：Java /manage/auth 签发 JWT → 全局 token 供 Python/Java 请求携带。
 * 演示降级：Java 不可用时（本地无后端）登录失败给出明确提示，不静默。 
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { JAVA_BASE, request, setAuthRefresher, setAuthToken } from '@/api/client'

interface TokenResponse {
  accessToken: string
  refreshToken: string
  expiresIn: number
  userId: number
}

export interface MeView {
  userId: number
  username: string
  nickname: string
  level: string
  /** 社区展示名（社区 S3 · docs/47 §4.2；GET /auth/me 扩展字段） */
  handle?: string | null
  /** 头像色板（无 avatarUrl 时的兜底底色） */
  tint?: string | null
  /** 真实头像（相对路径，渲染前过 mediaUrl） */
  avatarUrl?: string | null
}

const TOKEN_KEY = 'vv_token'
const REFRESH_KEY = 'vv_refresh'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const refreshToken = ref<string | null>(localStorage.getItem(REFRESH_KEY))
  const me = ref<MeView | null>(null)
  /** 会话是否持久化（「记住我」；冷启动按 localStorage 反推：留有 refresh 凭证 = 曾勾选记住，2026-09-07） */
  const remembered = ref(localStorage.getItem(REFRESH_KEY) !== null)

  function persist(t: TokenResponse, remember = true) {
    token.value = t.accessToken
    refreshToken.value = t.refreshToken
    remembered.value = remember
    if (remember) {
      localStorage.setItem(TOKEN_KEY, t.accessToken)
      localStorage.setItem(REFRESH_KEY, t.refreshToken)
    } else {
      // 不记住：仅内存会话（关闭应用/页面即登出）；顺手清掉可能残留的旧持久化凭证
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(REFRESH_KEY)
    }
    setAuthToken(t.accessToken)
  }

  function clear() {
    token.value = null
    refreshToken.value = null
    me.value = null
    remembered.value = false
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    setAuthToken(null)
  }

  async function login(username: string, password: string, remember = true) {
    const resp = await request<TokenResponse>(
      '/auth/login',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      },
      JAVA_BASE,
    )
    persist(resp.data, remember)
    await fetchMe()
  }

  async function register(payload: Record<string, string>, remember = true) {
    const resp = await request<TokenResponse>(
      '/auth/register',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
      JAVA_BASE,
    )
    persist(resp.data, remember)
    await fetchMe()
  }

  /** 忘记密码：演示环境无邮件/短信通道 → 落管理员工单（Java /auth/forgot，防枚举同响应） */
  async function forgotPassword(username: string) {
    const resp = await request<string>(
      '/auth/forgot',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username }),
      },
      JAVA_BASE,
    )
    return resp.data ?? '已收到申请，管理员将尽快处理'
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      const resp = await request<MeView>('/auth/me', undefined, JAVA_BASE)
      me.value = resp.data
    } catch {
      me.value = null
    }
  }

  async function refresh() {
    if (!refreshToken.value) return false
    try {
      const resp = await request<TokenResponse>(
        '/auth/refresh',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refreshToken: refreshToken.value }),
        },
        JAVA_BASE,
      )
      persist(resp.data, remembered.value)
      return true
    } catch {
      clear()
      return false
    }
  }

  /** 登出：先服务端吊销该用户全部 refresh token（docs/18 §3-J1 · 2026-09-07 补：只清本地则 30 天窗口内仍可续命），再清本地。 */
  async function logout() {
    if (token.value) {
      try {
        await request('/auth/logout', { method: 'POST' }, JAVA_BASE)
      } catch (err) {
        // 吊销失败（网络/令牌已失效）不阻塞本地登出——但必须可观测（2026-09-07 评审：此前静默吞掉，
        // 网络失败时服务端 token 未吊销、用户毫不知情）
        console.warn('logout: 服务端吊销失败（本地已登出；refresh token 可能仍有效）', err)
      }
    }
    clear()
  }

  return { token, refreshToken, me, remembered, login, register, forgotPassword, fetchMe, refresh, logout, clear }
})

/** 启动时恢复会话（路由守卫调用一次）。 */
export async function bootstrapAuth() {
  const store = useAuthStore()
  setAuthToken(store.token)
  // 会话中途 401 静默续期（docs/18 F3；client.ts 注入式钩子，2026-09-05 补：原来只有启动时刷新）
  setAuthRefresher(() => store.refresh())
  if (store.token) {
    await store.refresh().catch(() => undefined)
    // 恢复用户态：只换 token 不拉 /auth/me → 整页刷新后 me=null，UI 显示「未登录/同学」而接口
    // 照常带 token 工作（2026-09-07 修复；login/register 均调 fetchMe，故登录后正常）
    await store.fetchMe()
  }
}
