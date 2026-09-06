import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import LoginView from '@/views/LoginView.vue'

const loginMock = vi.fn().mockResolvedValue(undefined)

vi.mock('@/stores/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/stores/auth')>()
  return { ...actual, useAuthStore: () => ({ login: loginMock, clear: vi.fn(), me: null }) }
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/login', component: LoginView }, { path: '/m/home', component: { template: '<div/>' } }],
})

beforeEach(() => {
  setActivePinia(createPinia())
  loginMock.mockClear()
})

describe('LoginView（退出后/未登录入口 · 2026-09-06 修正）', () => {
  it('Sign Up = 一键默认演示账号：自动填入 demoadult/demo123456 并登录进入', async () => {
    await router.push('/login')
    await router.isReady()
    const wrapper = mount(LoginView, { global: { plugins: [router] } })

    const signUp = wrapper.findAll('span.span').find((s) => s.text().includes('Sign Up'))
    expect(signUp).toBeTruthy()
    await signUp!.trigger('click') // "Don't have an account? Sign Up" 的 Sign Up
    await flushPromises()

    expect(loginMock).toHaveBeenCalledWith('demoadult', 'demo123456')
    // 输入框回填可见（用户可感知）
    expect((wrapper.get('#vv-email').element as HTMLInputElement).value).toBe('demoadult')
    expect((wrapper.get('#vv-password').element as HTMLInputElement).value).toBe('demo123456')
  })

  it('Sign In：输入账号密码提交 → login 携带输入值', async () => {
    await router.push('/login')
    await router.isReady()
    const wrapper = mount(LoginView, { global: { plugins: [router] } })

    await wrapper.get('#vv-email').setValue('demoteen')
    await wrapper.get('#vv-password').setValue('demo123456')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(loginMock).toHaveBeenCalledWith('demoteen', 'demo123456')
  })
})
