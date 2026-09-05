import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import MobileLearnView from '@/views/mobile/MobileLearnView.vue'
import MobileNotesView from '@/views/mobile/MobileNotesView.vue'

const routes = [
  { path: '/m/home', component: { template: '<div/>' } },
  { path: '/m/search', component: { template: '<div/>' } },
  { path: '/m/learn', component: MobileLearnView },
  { path: '/m/notes', component: MobileNotesView },
  { path: '/m/chat', component: { template: '<div/>' } },
  { path: '/m/chat/:sceneId?', component: { template: '<div/>' } },
  { path: '/m/free-chat', component: { template: '<div/>' } },
  { path: '/m/sing', component: { template: '<div/>' } },
  { path: '/m/messages', component: { template: '<div/>' } },
  { path: '/m/messages/:id', component: { template: '<div/>' } },
  { path: '/m/me', component: { template: '<div/>' } },
  { path: '/m/report', component: { template: '<div/>' } },
  { path: '/m/compose', component: { template: '<div/>' } },
]

const router = createRouter({ history: createMemoryHistory(), routes })

beforeEach(() => setActivePinia(createPinia()))

async function mountAt(path: string) {
  await router.push(path)
  await router.isReady()
  return mount(MobileTabBar, { global: { plugins: [router] } })
}

describe('MobileTabBar（双场景分组）', () => {
  it('社区组：5 位（社区/搜索/＋发帖/学习出口/私信）', async () => {
    const wrapper = await mountAt('/m/home')
    expect(wrapper.find('.u-tabbar').exists()).toBe(true)
    const links = wrapper.findAll('a')
    expect(links).toHaveLength(5)
    expect(wrapper.find('a[aria-label="搜索"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="发帖"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="学习"]').exists()).toBe(true) // 出口
    expect(wrapper.find('a[aria-label="私信"]').exists()).toBe(true)
    expect(links[2].attributes('aria-label')).toBe('发帖') // 中央对称
  })

  it('学习组：5 位（Home 出口/场景对话/笔记中央/唱吧/自由对话）', async () => {
    const wrapper = await mountAt('/m/learn')
    expect(wrapper.find('.u-tabbar').exists()).toBe(true)
    const links = wrapper.findAll('a')
    expect(links).toHaveLength(5)
    expect(wrapper.find('a[aria-label="返回社区"]').exists()).toBe(true) // Home 出口
    expect(wrapper.find('a[aria-label="场景对话"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="唱吧"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="自由对话"]').exists()).toBe(true)
    expect(links[2].attributes('aria-label')).toBe('笔记') // 中央对称
  })

  it('学习场景内全部显示学习组（chat/场景直入/free-chat/sing/notes）', async () => {
    for (const p of ['/m/chat', '/m/chat/3', '/m/free-chat', '/m/sing', '/m/notes']) {
      const wrapper = await mountAt(p)
      expect(wrapper.find('.u-tabbar').exists(), p).toBe(true)
      expect(wrapper.find('a[aria-label="返回社区"]').exists(), p).toBe(true)
    }
  })

  it('社区场景内（会话/我的/报告）显示社区组；发帖沉浸页隐藏', async () => {
    for (const p of ['/m/messages/1', '/m/me', '/m/report']) {
      const wrapper = await mountAt(p)
      expect(wrapper.find('.u-tabbar').exists(), p).toBe(true)
      expect(wrapper.find('a[aria-label="搜索"]').exists(), p).toBe(true)
    }
    const compose = await mountAt('/m/compose')
    expect(compose.find('.u-tabbar').exists()).toBe(false)
  })
})

describe('MobileLearnView（学习 · Duolingo 式画像）', () => {
  it('渲染画像主卡：LV 徽章 / 等级名 / 经验条 / 速览与趋势', async () => {
    await router.push('/m/learn')
    await router.isReady()
    const wrapper = mount(MobileLearnView, { global: { plugins: [router] } })
    const text = wrapper.text()
    expect(text).toContain('LV3')
    expect(text).toContain('对话能手')
    expect(text).toContain('XP')
    expect(text).toContain('薄弱音素')
    expect(text).toContain('流利度趋势')
    // 旧占位/旧练习内容不应保留
    expect(text).not.toContain('建设中')
    expect(text).not.toContain('今日目标')
  })
})

describe('MobileNotesView（笔记 · 词汇速记演示）', () => {
  it('渲染笔记列表；分类切换；收藏 toggle', async () => {
    await router.push('/m/notes')
    await router.isReady()
    const wrapper = mount(MobileNotesView, { global: { plugins: [router] } })
    expect(wrapper.text()).toContain('pick up')
    expect(wrapper.text()).toContain('影子跟读法')

    // 分类切换 → 文化
    await wrapper.findAll('.u-x-tab')[3].trigger('click' as never)
    expect(wrapper.text()).toContain('kyushoku')
    expect(wrapper.text()).not.toContain('pick up')

    // 收藏 toggle（序号 1 = run out of，初始未收藏 → 点击收藏）
    await wrapper.findAll('.u-x-tab')[0].trigger('click' as never)
    const stars = wrapper.findAll('.u-notes__star')
    expect(stars[1].classes()).not.toContain('is-starred')
    await stars[1].trigger('click')
    expect(stars[1].classes()).toContain('is-starred')
  })
})
