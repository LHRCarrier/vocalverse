import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { clearTokens, consoleApi, getAccessToken, saveTokens } from '@/api'
import type { ConsoleProfile } from '@/api'

/**
 * 控制台身份 store（docs/50 §4）。
 *
 * 三个刻意的设计：
 * 1. **与 App 登录态隔离**——令牌键 `vv_console_*`，与 `vv_token` 互不影响；
 * 2. `hasPermission` 只做**前端裁剪**（菜单/按钮），后端逐请求校验才是安全边界；
 * 3. `super` 的 `*` 通配已在服务端展开为完整权限码列表，故前端无需通配逻辑
 *    （少一条"前端以为自己是超管"的错误面）。
 *
 * ⚠️ 登录响应的形状（2026-09-10 修正）：`POST /auth/login` 回的是
 * `ConsoleAuthController.SessionView` —— `token` + 平铺的主体摘要
 * （`adminUserId`/`username`/`displayName`/`roleCode`/`permissions`），**没有** `profile` 对象。
 * 因此登录后立即再打一次 `GET /auth/me` 拿 `MeView`（它才有 `roleName`/`sessionId`）；
 * 令牌先落盘（`saveTokens`）保证那次 `/me` 带上 Authorization。
 */
export const useAuthStore = defineStore('console-auth', () => {
  const profile = ref<ConsoleProfile | null>(null)
  const accessToken = ref<string | null>(getAccessToken())
  const loading = ref(false)

  const isLoggedIn = computed(() => Boolean(accessToken.value))
  const permissions = computed<string[]>(() => profile.value?.permissions ?? [])
  /** 真实字段是扁平 `roleCode`（`MeView`），不是 v1 以为的 `profile.role.code` */
  const roleCode = computed(() => profile.value?.roleCode ?? '')
  /** 当前会话 id（`MeView.sessionId`）：会话列表据此标出"就是这一条"，不靠猜 */
  const sessionId = computed<number | null>(() => profile.value?.sessionId ?? null)

  function hasPermission(code: string | string[] | null | undefined): boolean {
    if (!code) return true
    const list = Array.isArray(code) ? code : [code]
    return list.every((c) => permissions.value.includes(c))
  }

  /** 满足其一即可（菜单项用） */
  function hasAny(codes: string | string[]): boolean {
    const list = Array.isArray(codes) ? codes : [codes]
    if (list.length === 0) return true
    return list.some((c) => permissions.value.includes(c))
  }

  async function login(username: string, password: string): Promise<void> {
    loading.value = true
    try {
      const session = await consoleApi.login(username, password)
      saveTokens(session.token)
      accessToken.value = session.token.accessToken
      // SessionView 没有 MeView 的 roleName/sessionId —— 补一次 /me，别用半成品档案渲染侧栏
      await fetchMe()
    } finally {
      loading.value = false
    }
  }

  async function fetchMe(): Promise<void> {
    profile.value = await consoleApi.me()
  }

  function clear(): void {
    clearTokens()
    accessToken.value = null
    profile.value = null
  }

  async function logout(): Promise<void> {
    try {
      await consoleApi.logout()
    } catch {
      // 登出接口失败不阻塞本地清理（服务端会话会在 TTL 后自然过期）
    }
    clear()
  }

  return {
    profile,
    accessToken,
    loading,
    isLoggedIn,
    permissions,
    roleCode,
    sessionId,
    hasPermission,
    hasAny,
    login,
    fetchMe,
    logout,
    clear,
  }
})
