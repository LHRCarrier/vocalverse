import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileTabBar from '@/components/mobile/MobileTabBar.vue'

const routes = [
  { path: '/m/home', component: { template: '<div/>' } },
  { path: '/m/search', component: { template: '<div/>' } },
  { path: '/m/chat', component: { template: '<div/>' } },
  { path: '/m/chat/:sceneId?', component: { template: '<div/>' } },
  { path: '/m/sing', component: { template: '<div/>' } },
  { path: '/m/messages', component: { template: '<div/>' } },
  { path: '/m/messages/:id', component: { template: '<div/>' } },
  { path: '/m/me', component: { template: '<div/>' } },
  { path: '/m/report', component: { template: '<div/>' } },
  { path: '/m/free-chat', component: { template: '<div/>' } },
]

const router = createRouter({ history: createMemoryHistory(), routes })

async function mountAt(path: string) {
  await router.push(path)
  await router.isReady()
  return mount(MobileTabBar, { global: { plugins: [router] } })
}

describe('MobileTabBar（全局显隐）', () => {
  it('tab 级页面显示：6 个入口（社区/搜索/发帖/口语/唱吧/私信）', async () => {
    const wrapper = await mountAt('/m/home')
    expect(wrapper.find('.u-tabbar').exists()).toBe(true)
    expect(wrapper.findAll('a')).toHaveLength(6)
    expect(wrapper.find('a[aria-label="搜索"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="发帖"]').exists()).toBe(true)
  })

  it('二级页隐藏（会话/报告/我的/自由对话）', async () => {
    for (const p of ['/m/messages/1', '/m/report', '/m/me', '/m/free-chat']) {
      const wrapper = await mountAt(p)
      expect(wrapper.find('.u-tabbar').exists(), p).toBe(false)
    }
  })

  it('口语场景直入（/m/chat/:id）仍显示', async () => {
    const wrapper = await mountAt('/m/chat/3')
    expect(wrapper.find('.u-tabbar').exists()).toBe(true)
  })
})
