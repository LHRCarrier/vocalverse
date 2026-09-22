import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import { useMessagesStore } from '@/stores/messages'
import MobileLearnView from '@/views/mobile/MobileLearnView.vue'
import MobileNotesView from '@/views/mobile/MobileNotesView.vue'

/** 学习画像接口桩（docs/53 P4：热力图改真实聚合；旧用例断言点格交互 → 提供两格数据） */
const today = new Date()
const key = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const yesterday = new Date(today)
yesterday.setDate(today.getDate() - 1)

vi.mock('@/api/stats', () => ({
  fetchLearnOverview: vi.fn(async () => ({
    profile_line: '近 30 天练了 3 次',
    heatmap: [
      { date: key(yesterday), count: 3, level: 1 },
      { date: key(today), count: 7, level: 2 },
    ],
    modules: {
      words: { summary: 'w' },
      community: { summary: 'c' },
      speaking: { summary: 's' },
      practice: { summary: 'p' },
    },
    generated_at: '2026-09-21T00:00:00+00:00',
  })),
}))
vi.mock('@/api/reco', () => ({ fetchItemsRecommendations: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/events', () => ({ track: vi.fn() }))
/* 笔记页接真（docs/53 P5）：跨章批注来自 /reading/notes */
vi.mock('@/api/reading', () => ({
  fetchNotes: vi.fn(async () => ({
    items: [
      {
        id: 1,
        kind: 'note',
        chapter_id: 5,
        book_id: 2,
        chapter_title: 'Chapter 1',
        book_title: 'Demo Book',
        start_offset: 0,
        end_offset: 5,
        content_version: 1,
        text_snippet: 'Alice knew',
        note: '过去式',
        created_at: '2026-09-21T10:00:00+00:00',
      },
    ],
    has_more: false,
  })),
}))

const routes = [
  { path: '/m/home', component: { template: '<div/>' } },
  { path: '/m/search', component: { template: '<div/>' } },
  { path: '/m/learn', component: MobileLearnView },
  { path: '/m/learn/:module', component: { template: '<div/>' } },
  { path: '/m/checkin', component: { template: '<div/>' } },
  { path: '/m/notes', component: MobileNotesView },
  { path: '/m/tavern', component: { template: '<div/>' } },
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

  it('学习组：5 位（Home 出口/酒馆中央/笔记/唱吧/自由对话）', async () => {
    const wrapper = await mountAt('/m/learn')
    expect(wrapper.find('.u-tabbar').exists()).toBe(true)
    const links = wrapper.findAll('a')
    expect(links).toHaveLength(5)
    expect(wrapper.find('a[aria-label="返回社区"]').exists()).toBe(true) // Home 出口
    expect(wrapper.find('a[aria-label="酒馆"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="唱吧"]').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="自由对话"]').exists()).toBe(true)
    expect(links[2].attributes('aria-label')).toBe('笔记') // 中央对称
  })

  it('学习场景内全部显示学习组（tavern/free-chat/sing/notes/learn:module）', async () => {
    for (const p of ['/m/tavern', '/m/free-chat', '/m/sing', '/m/notes', '/m/learn/speaking']) {
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

  it('通知 tab 显示全局未读角标（私信未读；>99 → 99+）', async () => {
    const wrapper = await mountAt('/m/home')
    const messages = useMessagesStore()
    messages.unreadTotal = 7
    await wrapper.vm.$nextTick()
    expect(wrapper.find('a[aria-label="通知"] .u-badge').text()).toBe('7')

    messages.unreadTotal = 120
    await wrapper.vm.$nextTick()
    expect(wrapper.find('a[aria-label="通知"] .u-badge').text()).toBe('99+')
  })

  it('打卡页属学习组（底栏保持可见）', async () => {
    const wrapper = await mountAt('/m/checkin')
    expect(wrapper.find('.u-tabbar').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="返回社区"]').exists()).toBe(true)
  })
})

describe('MobileLearnView（我的学习 · v4 画像总览 2026-09-09）', () => {
  it('渲染欢迎定位 + 识别行 + 热力图 + 6 模块列表（读书域并入 2026-09-10）', async () => {
    // XP/等级服务端化（docs/53 P5）：冷启动展示缓存快照
    localStorage.setItem(
      'vv_progress',
      JSON.stringify({ xp: 320, level: 3, title: '对话能手', base: 250, next: 500 }),
    )
    await router.push('/m/learn')
    await router.isReady()
    const wrapper = mount(MobileLearnView, { global: { plugins: [router] } })
    const text = wrapper.text()
    localStorage.removeItem('vv_progress')
    expect(text).toContain('Hi') // 欢迎定位行
    expect(text).toContain('LV3')
    expect(text).toContain('XP')
    // 6 个模块（我的单词/书房 为读书域入口，docs/45）
    for (const m of ['我的单词', '书房', '社区足迹', '我的发音', '冒险进度']) {
      expect(text).toContain(m)
    }
    expect(text).toContain('阅读查词即收')
    expect(text).toContain('发音 82 · 流利 78 · 语法 85')
    // 热力图 = 12 周 × 7 天 = 84 格；无图例/切换
    expect(wrapper.findAll('.u-learn-heat__cell').length).toBe(12 * 7)
    expect(wrapper.findAll('.u-learn-heat__mode').length).toBe(0)
    // 旧内容不应保留
    expect(text).not.toContain('建设中')
    expect(text).not.toContain('今日目标')
    expect(text).not.toContain('薄弱音素')
  })

  it('模块点击跳转（我的单词 → /m/vocab 读书域名入口）', async () => {
    await router.push('/m/learn')
    await router.isReady()
    const wrapper = mount(MobileLearnView, { global: { plugins: [router] } })
    await wrapper.findAll('.u-learn-module')[0].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/m/vocab')
  })

  it('热力图：点格 → 右下角经验更新（真实聚合：接口两格数据）', async () => {
    await router.push('/m/learn')
    await router.isReady()
    const wrapper = mount(MobileLearnView, { global: { plugins: [router] } })
    await flushPromises()
    const before = wrapper.find('.u-learn-heat__xp').text()
    await wrapper.findAll('.u-learn-heat__cell:not(.future):not(.lv0)')[0].trigger('click')
    expect(wrapper.find('.u-learn-heat__xp').text()).not.toBe(before)
  })
})

describe('MobileNotesView（笔记接真 · docs/53 P5）', () => {
  it('渲染跨章批注；分类切换走服务端 kind 过滤', async () => {
    await router.push('/m/notes')
    await router.isReady()
    const wrapper = mount(MobileNotesView, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('过去式')
    expect(wrapper.text()).toContain('Demo Book · Chapter 1')
    expect(wrapper.text()).not.toContain('pick up') // 演示数据已删除

    await wrapper.findAll('.u-x-tab')[2].trigger('click' as never)
    await flushPromises()
    const { fetchNotes } = await import('@/api/reading')
    expect(fetchNotes).toHaveBeenLastCalledWith('note')
  })
})
