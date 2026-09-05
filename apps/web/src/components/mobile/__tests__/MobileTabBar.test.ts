import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import MobilePracticeView from '@/views/mobile/MobilePracticeView.vue'

beforeEach(() => setActivePinia(createPinia()))

const routes = [
  { path: '/m/home', component: { template: '<div/>' } },
  { path: '/m/search', component: { template: '<div/>' } },
  { path: '/m/practice', component: MobilePracticeView },
  { path: '/m/chat', component: { template: '<div/>' } },
  { path: '/m/chat/:sceneId?', component: { template: '<div/>' } },
  { path: '/m/free-chat', component: { template: '<div/>' } },
  { path: '/m/sing', component: { template: '<div/>' } },
  { path: '/m/messages', component: { template: '<div/>' } },
  { path: '/m/messages/:id', component: { template: '<div/>' } },
  { path: '/m/me', component: { template: '<div/>' } },
  { path: '/m/report', component: { template: '<div/>' } },
]

const router = createRouter({ history: createMemoryHistory(), routes })

async function mountAt(path: string) {
  await router.push(path)
  await router.isReady()
  return mount(MobileTabBar, { global: { plugins: [router] } })
}

describe('MobileTabBar（全局显隐 · 5 位对称）', () => {
  it('tab 级页面显示：5 个入口，＋ 发帖在中央', async () => {
    const wrapper = await mountAt('/m/home')
    expect(wrapper.find('.u-tabbar').exists()).toBe(true)
    const links = wrapper.findAll('a')
    expect(links).toHaveLength(5)
    expect(wrapper.find('a[aria-label="搜索"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="发帖"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="练习"]').exists()).toBe(true)
    // 中央按钮位于第 3 位（左右各 2）→ 对称
    expect(links[2].attributes('aria-label')).toBe('发帖')
  })

  it('二级页隐藏（会话/报告/我的/自由对话/口语场景/唱吧）', async () => {
    for (const p of ['/m/messages/1', '/m/report', '/m/me', '/m/free-chat', '/m/chat', '/m/chat/3', '/m/sing']) {
      const wrapper = await mountAt(p)
      expect(wrapper.find('.u-tabbar').exists(), p).toBe(false)
    }
  })
})

describe('MobilePracticeView（练习 Hub）', () => {
  it('渲染三张入口卡：场景对话 / 自由对话 / 唱吧', async () => {
    await router.push('/m/practice')
    await router.isReady()
    const wrapper = mount(MobilePracticeView, { global: { plugins: [router] } })
    const text = wrapper.text()
    expect(text).toContain('场景对话')
    expect(text).toContain('自由对话')
    expect(text).toContain('唱吧')
    expect(wrapper.findAll('.u-hub-card')).toHaveLength(3)
  })
})
