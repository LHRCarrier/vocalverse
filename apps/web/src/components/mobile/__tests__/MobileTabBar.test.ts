import { beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import MobileLearnView from '@/views/mobile/MobileLearnView.vue'
import MobileNotesView from '@/views/mobile/MobileNotesView.vue'

const routes = [
  { path: '/m/home', component: { template: '<div/>' } },
  { path: '/m/search', component: { template: '<div/>' } },
  { path: '/m/learn', component: MobileLearnView },
  { path: '/m/learn/:module', component: { template: '<div/>' } },
  { path: '/m/notes', component: MobileNotesView },
  { path: '/m/chat', component: { template: '<div/>' } },
  { path: '/m/chat/:sceneId?', component: { template: '<div/>' } },
  { path: '/m/free-chat', component: { template: '<div/>' } },
  { path: '/m/sing', component: { template: '<div/>' } },
  { path: '/m/messages', component: { template: '<div/>' } },
  { path: '/m/messages/:id', component: { template: '<div/>' } },
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
  it('社区组：5 位（社区/搜索/＋发帖/学习出口/通知）', async () => {
    const wrapper = await mountAt('/m/home')
    expect(wrapper.find('.u-tabbar').exists()).toBe(true)
    const links = wrapper.findAll('a')
    expect(links).toHaveLength(5)
    expect(wrapper.find('a[aria-label="搜索"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="发帖"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="学习"]').exists()).toBe(true) // 出口
    expect(wrapper.find('a[aria-label="通知"]').exists()).toBe(true) // 私信收敛进通知中心
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

  it('学习场景内全部显示学习组（chat/场景直入/free-chat/sing/notes/learn:module）', async () => {
    for (const p of ['/m/chat', '/m/chat/3', '/m/free-chat', '/m/sing', '/m/notes', '/m/learn/speaking']) {
      const wrapper = await mountAt(p)
      expect(wrapper.find('.u-tabbar').exists(), p).toBe(true)
      expect(wrapper.find('a[aria-label="返回社区"]').exists(), p).toBe(true)
    }
  })

  it('社区场景内（会话/报告）显示社区组；发帖沉浸页隐藏', async () => {
    for (const p of ['/m/messages/1', '/m/report']) {
      const wrapper = await mountAt(p)
      expect(wrapper.find('.u-tabbar').exists(), p).toBe(true)
      expect(wrapper.find('a[aria-label="搜索"]').exists(), p).toBe(true)
    }
    const compose = await mountAt('/m/compose')
    expect(compose.find('.u-tabbar').exists()).toBe(false)
  })
})

describe('MobileLearnView（我的学习 · v4 画像总览 2026-09-09）', () => {
  it('渲染欢迎定位 + 识别行 + 热力图 + 4 模块列表', async () => {
    await router.push('/m/learn')
    await router.isReady()
    const wrapper = mount(MobileLearnView, { global: { plugins: [router] } })
    const text = wrapper.text()
    expect(text).toContain('Hi') // 欢迎定位行
    expect(text).toContain('LV3')
    expect(text).toContain('XP')
    // 4 个模块
    for (const m of ['我的单词', '社区足迹', '我的发音', '练习情况']) {
      expect(text).toContain(m)
    }
    expect(text).toContain('收录 24 词')
    expect(text).toContain('发音 82 · 流利 78 · 语法 85')
    // 热力图 = 12 周 × 7 天 = 84 格；无图例/切换
    expect(wrapper.findAll('.u-learn-heat__cell').length).toBe(12 * 7)
    expect(wrapper.findAll('.u-learn-heat__mode').length).toBe(0)
    // 旧内容不应保留
    expect(text).not.toContain('建设中')
    expect(text).not.toContain('今日目标')
    expect(text).not.toContain('薄弱音素')
  })

  it('模块点击跳转 /m/learn/:module', async () => {
    await router.push('/m/learn')
    await router.isReady()
    const wrapper = mount(MobileLearnView, { global: { plugins: [router] } })
    await wrapper.findAll('.u-learn-module')[2].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/m/learn/speaking')
  })

  it('热力图：点格 → 右下角经验更新', async () => {
    await router.push('/m/learn')
    await router.isReady()
    const wrapper = mount(MobileLearnView, { global: { plugins: [router] } })
    const before = wrapper.find('.u-learn-heat__xp').text()
    await wrapper.findAll('.u-learn-heat__cell:not(.future)')[0].trigger('click')
    expect(wrapper.find('.u-learn-heat__xp').text()).not.toBe(before)
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
