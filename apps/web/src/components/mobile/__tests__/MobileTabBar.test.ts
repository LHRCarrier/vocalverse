import { beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import MobileNotesView from '@/views/mobile/MobileNotesView.vue'
import MobilePracticeView from '@/views/mobile/MobilePracticeView.vue'

const routes = [
  { path: '/m/home', component: { template: '<div/>' } },
  { path: '/m/search', component: { template: '<div/>' } },
  { path: '/m/practice', component: MobilePracticeView },
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
  it('社区组：5 位（社区/搜索/＋发帖/练习出口/私信）', async () => {
    const wrapper = await mountAt('/m/home')
    expect(wrapper.find('.u-tabbar').exists()).toBe(true)
    const links = wrapper.findAll('a')
    expect(links).toHaveLength(5)
    expect(wrapper.find('a[aria-label="搜索"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="发帖"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="练习"]').exists()).toBe(true) // 出口
    expect(wrapper.find('a[aria-label="私信"]').exists()).toBe(true)
    expect(links[2].attributes('aria-label')).toBe('发帖') // 中央对称
  })

  it('练习组：5 位（Home 出口/场景对话/笔记中央/唱吧/自由对话）', async () => {
    const wrapper = await mountAt('/m/practice')
    expect(wrapper.find('.u-tabbar').exists()).toBe(true)
    const links = wrapper.findAll('a')
    expect(links).toHaveLength(5)
    expect(wrapper.find('a[aria-label="返回社区"]').exists()).toBe(true) // Home 出口
    expect(wrapper.find('a[aria-label="场景对话"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="唱吧"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="自由对话"]').exists()).toBe(true)
    expect(links[2].attributes('aria-label')).toBe('笔记') // 中央对称（2026-09-05 组长拍板：中央=笔记）
  })

  it('练习场景内全部显示练习组（chat/场景直入/free-chat/sing/notes）', async () => {
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

describe('MobilePracticeView（练习首页）', () => {
  it('渲染完整首页结构：今日目标 / 统计 / 场景推荐（fallback）/ 自由对话 / 唱吧精选', async () => {
    await router.push('/m/practice')
    await router.isReady()
    const wrapper = mount(MobilePracticeView, { global: { plugins: [router] } })
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('今日目标')
    expect(text).toContain('连续 12 天')
    expect(text).toContain('场景对话')
    expect(text).toContain('AI 自由对话')
    expect(text).toContain('本周精选') // 唱吧精选暗卡 chip
    expect(text).toContain('Perfect Night')
    expect(text).toContain('开始练习')
    // 场景 ×3 + 自由对话 = 4 张 u-hub-card；唱吧精选 = 唯一深色卡
    expect(wrapper.findAll('.u-hub-card')).toHaveLength(4)
    expect(wrapper.findAll('.u-dark-card')).toHaveLength(1)
  })
})
