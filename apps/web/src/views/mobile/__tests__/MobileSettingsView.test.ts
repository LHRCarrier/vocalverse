/**
 * 设置与隐私三页（docs/53 P5 ④）：非 toast —— 帮助与反馈提交真实工单、
 * 数据与隐私/关于为可导航真实页。
 */
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileSettingsView from '@/views/mobile/MobileSettingsView.vue'

const mocks = vi.hoisted(() => ({ createTicket: vi.fn(), fetchMyTickets: vi.fn() }))

vi.mock('@/api/tickets', () => ({
  createTicket: mocks.createTicket,
  fetchMyTickets: mocks.fetchMyTickets,
}))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/settings/:section', component: MobileSettingsView },
    { path: '/m/home', component: { template: '<div/>' } },
  ],
})

async function mountAt(section: string) {
  await router.push(`/m/settings/${section}`)
  await router.isReady()
  const wrapper = mount(MobileSettingsView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

enableAutoUnmount(afterEach)

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  localStorage.setItem('vv_token', 't')
  mocks.fetchMyTickets.mockResolvedValue([])
})

afterEach(() => localStorage.clear())

describe('设置与隐私三页（docs/53 P5）', () => {
  it('help：提交反馈调用真实工单接口并置顶展示', async () => {
    mocks.createTicket.mockResolvedValue({
      id: 9,
      kind: 'bug',
      content: '录音后闪退',
      status: 'open',
      createdAt: '2026-09-21T10:00:00Z',
    })
    const wrapper = await mountAt('help')
    expect(mocks.fetchMyTickets).toHaveBeenCalled()

    await wrapper.findAll('.u-set__chips .u-chip')[1].trigger('click') // 问题反馈
    await wrapper.get('.u-set__textarea').setValue('录音后闪退')
    await wrapper.get('.u-btn--primary').trigger('click')
    await flushPromises()

    expect(mocks.createTicket).toHaveBeenCalledWith({ kind: 'bug', content: '录音后闪退', title: undefined })
    expect(wrapper.text()).toContain('待处理')
    expect(wrapper.text()).toContain('录音后闪退')
  })

  it('help：提交失败内联提示（不清空输入）', async () => {
    mocks.createTicket.mockRejectedValue(new Error('网络错误'))
    const wrapper = await mountAt('help')
    await wrapper.get('.u-set__textarea').setValue('打不开阅读器')
    await wrapper.get('.u-btn--primary').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('网络错误')
    expect((wrapper.get('.u-set__textarea').element as HTMLTextAreaElement).value).toBe('打不开阅读器')
  })

  it('privacy / about：渲染真实页面内容（非 toast）', async () => {
    const privacy = await mountAt('privacy')
    expect(privacy.text()).toContain('我们收集什么')
    const about = await mountAt('about')
    expect(about.text()).toContain('VocalVerse 声语界')
    expect(about.text()).toContain('素材与致谢')
  })
})
