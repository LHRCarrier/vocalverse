/**
 * 认证 store（docs/18 §3-J1）：Java /manage/auth 签发 JWT → 全局 token 供 Python/Java 请求携带。
 * 演示降级：Java 不可用时（本地无后端）登录失败给出明确提示，不静默。 
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { request, setAuthRefresher, setAuthToken } from '@/api/client'

interface TokenResponse {
  accessToken: string
  refreshToken: string
  expiresIn: number
  userId: number
}

interface MeView {
  userId: number
  username: string
  nickname: string
  level: string
}

const TOKEN_KEY = 'vv_token'
const REFRESH_KEY = 'vv_refresh'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const refreshToken = ref<string | null>(localStorage.getItem(REFRESH_KEY))
  const me = ref<MeView | null>(null)

  function persist(t: TokenResponse) {
    token.value = t.accessToken
    refreshToken.value = t.refreshToken
    localStorage.setItem(TOKEN_KEY, t.accessToken)
    localStorage.setItem(REFRESH_KEY, t.refreshToken)
    setAuthToken(t.accessToken)
  }

  function clear() {
    token.value = null
    refreshToken.value = null
    me.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    setAuthToken(null)
  }

  async function login(username: string, password: string) {
    const resp = await request<TokenResponse>(
      '/auth/login',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      },
      '/manage',
    )
    persist(resp.data)
    await fetchMe()
  }

  async function register(payload: Record<string, string>) {
    const resp = await request<TokenResponse>(
      '/auth/register',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
      '/manage',
    )
    persist(resp.data)
    await fetchMe()
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      const resp = await request<MeView>('/auth/me', undefined, '/manage')
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
        '/manage',
      )
      persist(resp.data)
      return true
    } catch {
      clear()
      return false
    }
  }

  return { token, refreshToken, me, login, register, fetchMe, refresh, clear }
})

/** 启动时恢复会话（路由守卫调用一次）。 */
export async function bootstrapAuth() {
  const store = useAuthStore()
  setAuthToken(store.token)
  // 会话中途 401 静默续期（docs/18 F3；client.ts 注入式钩子，2026-09-05 补：原来只有启动时刷新）
  setAuthRefresher(() => store.refresh())
  if (store.token) {
    await store.refresh().catch(() => undefined)
  }
}
