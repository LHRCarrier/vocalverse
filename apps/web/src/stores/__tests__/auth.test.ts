import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { bootstrapAuth, useAuthStore } from '@/stores/auth'
import { request, setAuthRefresher, setAuthToken } from '@/api/client'

vi.mock('@/api/client', () => ({
  request: vi.fn(),
  setAuthToken: vi.fn(),
  setAuthRefresher: vi.fn(),
}))

describe('bootstrapAuth（启动恢复会话）', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('有 token：换新 token 后拉取 /auth/me 恢复用户态（修复前 me 保持 null → UI 未登录）', async () => {
    localStorage.setItem('vv_token', 'old-token')
    localStorage.setItem('vv_refresh', 'old-refresh')
    vi.mocked(request)
      .mockResolvedValueOnce({
        code: 0,
        message: 'ok',
        data: { accessToken: 'new-token', refreshToken: 'new-refresh', expiresIn: 3600, userId: 1 },
      })
      .mockResolvedValueOnce({
        code: 0,
        message: 'ok',
        data: { userId: 1, username: 'test01', nickname: '测试01', level: 'LV3' },
      })

    await bootstrapAuth()

    const store = useAuthStore()
    // 修复前：bootstrapAuth 只 refresh 不 fetchMe → me 为 null，抽屉/顶栏显示「同学/未登录」但接口正常
    expect(store.me?.nickname).toBe('测试01')
    expect(store.me?.username).toBe('test01')
    expect(request).toHaveBeenNthCalledWith(1, '/auth/refresh', expect.anything(), '/manage')
    expect(request).toHaveBeenNthCalledWith(2, '/auth/me', undefined, '/manage')
    // 初始恢复 + refresh 换新 token 各注入一次
    expect(setAuthToken).toHaveBeenCalledTimes(2)
    expect(setAuthRefresher).toHaveBeenCalledTimes(1)
  })

  it('无 token：不发任何请求，me 保持 null（未登录态）', async () => {
    await bootstrapAuth()
    expect(request).not.toHaveBeenCalled()
    expect(useAuthStore().me).toBeNull()
  })

  it('login(remember=false)：仅内存会话，不写 localStorage（关闭/刷新即登出）', async () => {
    vi.mocked(request)
      .mockResolvedValueOnce({
        code: 0,
        message: 'ok',
        data: { accessToken: 'mem-token', refreshToken: 'mem-refresh', expiresIn: 3600, userId: 1 },
      })
      .mockResolvedValueOnce({ code: 0, message: 'ok', data: { userId: 1, username: 'u1', nickname: '用户1', level: 'LV1' } })
    const store = useAuthStore()
    await store.login('u1', 'password123', false)
    expect(store.token).toBe('mem-token')
    expect(store.me?.nickname).toBe('用户1')
    expect(localStorage.getItem('vv_token')).toBeNull()
    expect(localStorage.getItem('vv_refresh')).toBeNull()
  })

  it('login(remember=true)：凭证持久化到 localStorage（默认）', async () => {
    vi.mocked(request)
      .mockResolvedValueOnce({
        code: 0,
        message: 'ok',
        data: { accessToken: 'persist-token', refreshToken: 'persist-refresh', expiresIn: 3600, userId: 1 },
      })
      .mockResolvedValueOnce({ code: 0, message: 'ok', data: { userId: 1, username: 'u1', nickname: '用户1', level: 'LV1' } })
    const store = useAuthStore()
    await store.login('u1', 'password123')
    expect(store.remembered).toBe(true)
    expect(localStorage.getItem('vv_token')).toBe('persist-token')
    expect(localStorage.getItem('vv_refresh')).toBe('persist-refresh')
  })

  it('logout：先调 /auth/logout 服务端吊销，再清空本地凭证', async () => {
    localStorage.setItem('vv_token', 't')
    localStorage.setItem('vv_refresh', 'r')
    setActivePinia(createPinia()) // 重新取 store 以读到预置 localStorage
    const store = useAuthStore()
    await store.logout()
    expect(request).toHaveBeenCalledWith('/auth/logout', { method: 'POST' }, '/manage')
    expect(localStorage.getItem('vv_token')).toBeNull()
    expect(localStorage.getItem('vv_refresh')).toBeNull()
    expect(store.token).toBeNull()
    expect(store.remembered).toBe(false)
  })

  it('logout 吊销失败：仍清空本地 + console.warn 可观测（评审建议：此前静默吞掉）', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    localStorage.setItem('vv_token', 't')
    localStorage.setItem('vv_refresh', 'r')
    setActivePinia(createPinia())
    const store = useAuthStore()
    vi.mocked(request).mockRejectedValueOnce(new Error('network down'))
    await store.logout()
    expect(request).toHaveBeenCalledWith('/auth/logout', { method: 'POST' }, '/manage')
    expect(store.token).toBeNull()
    expect(localStorage.getItem('vv_token')).toBeNull()
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('服务端吊销失败'), expect.anything())
    warnSpy.mockRestore()
  })
})
