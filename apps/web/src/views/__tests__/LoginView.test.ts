import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import LoginView from '@/views/LoginView.vue'

const loginMock = vi.fn().mockResolvedValue(undefined)
const registerMock = vi.fn().mockResolvedValue(undefined)
const forgotPasswordMock = vi.fn().mockResolvedValue('已收到申请：管理员将尽快处理（演示环境无邮件通道，请留意管理员工单）')

vi.mock('@/stores/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/stores/auth')>()
  return {
    ...actual,
    useAuthStore: () => ({
      login: loginMock,
      register: registerMock,
      forgotPassword: forgotPasswordMock,
      clear: vi.fn(),
      me: null,
    }),
  }
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/login', component: LoginView }, { path: '/m/home', component: { template: '<div/>' } }],
})

beforeEach(() => {
  setActivePinia(createPinia())
  loginMock.mockClear()
  registerMock.mockClear()
  forgotPasswordMock.mockClear()
})

async function mountLogin() {
  await router.push('/login')
  await router.isReady()
  return mount(LoginView, { global: { plugins: [router] } })
}

/** 登录/注册成功后有 200ms 延时导航（组件行为）；等它完成，避免导航在测试环境拆除后才触发（history is not defined） */
function settleNavigate(ms = 260) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

describe('LoginView（登录/注册/忘记密码 · 2026-09-06 组长定案）', () => {
  it('Sign In：输入账号密码提交 → login 携带输入值 + 记住我（默认勾选）', async () => {
    const wrapper = await mountLogin()
    await wrapper.get('#vv-username').setValue('demoteen')
    await wrapper.get('#vv-password').setValue('demo123456')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(loginMock).toHaveBeenCalledWith('demoteen', 'demo123456', true)
    await settleNavigate()
  })

  it('Sign In 取消「记住我」：login 第三参为 false（关闭即登出）', async () => {
    const wrapper = await mountLogin()
    await wrapper.get('#vv-username').setValue('demoteen')
    await wrapper.get('#vv-password').setValue('demo123456')
    await wrapper.get('#remember').setValue(false)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(loginMock).toHaveBeenCalledWith('demoteen', 'demo123456', false)
    await settleNavigate()
  })

  it('Sign Up = 真实注册：切换注册表单 → 提交 → register({username, password, nickname, ageGroup})', async () => {
    const wrapper = await mountLogin()
    const signUp = wrapper.findAll('span.span').find((s) => s.text().includes('Sign Up'))
    expect(signUp).toBeTruthy()
    await signUp!.trigger('click')

    // 注册表单出现
    expect(wrapper.find('#reg-username').exists()).toBe(true)

    await wrapper.get('#reg-username').setValue('newuser')
    await wrapper.get('#reg-nickname').setValue('New User')
    await wrapper.get('#reg-password').setValue('password123')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(registerMock).toHaveBeenCalledWith(
      {
        username: 'newuser',
        password: 'password123',
        nickname: 'New User',
        ageGroup: 'adult',
      },
      true,
    )
    await settleNavigate()
  })

  it('Forgot password：切换申请表单 → 提交 → forgotPassword + 展示返回文案', async () => {
    const wrapper = await mountLogin()
    const forgot = wrapper.findAll('span.span').find((s) => s.text().includes('Forgot password?'))
    expect(forgot).toBeTruthy()
    await forgot!.trigger('click')

    expect(wrapper.find('#forgot-username').exists()).toBe(true)
    await wrapper.get('#forgot-username').setValue('demoadult')
    await wrapper.get('button.button-submit').trigger('click')
    await flushPromises()

    expect(forgotPasswordMock).toHaveBeenCalledWith('demoadult')
    expect(wrapper.text()).toContain('已收到申请：管理员将尽快处理')
    expect(wrapper.text()).toContain('Back to Sign In')
  })
})
