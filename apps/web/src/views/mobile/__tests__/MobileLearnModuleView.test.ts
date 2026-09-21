/**
 * 学习模块详情页接真（docs/53 P4 尾项）：四模块数据来自 /api/v1/stats/learn/{key}，
 * 空数据/接口失败有显式空态（不得回退演示帧）。
 */
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileLearnModuleView from '@/views/mobile/MobileLearnModuleView.vue'

const mocks = vi.hoisted(() => ({ fetchModule: vi.fn() }))

vi.mock('@/api/stats', () => ({ fetchLearnModule: mocks.fetchModule }))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/learn', component: { template: '<div/>' } },
    { path: '/m/learn/:module', component: MobileLearnModuleView },
    { path: '/m/vocab', component: { template: '<div/>' } },
  ],
})

async function mountAt(module: string) {
  await router.push(`/m/learn/${module}`)
  await router.isReady()
  const wrapper = mount(MobileLearnModuleView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

enableAutoUnmount(afterEach)

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('学习模块详情（docs/53 P4）', () => {
  it('speaking：渲染三维均分 / 趋势 / 薄弱音素（接口真值）', async () => {
    mocks.fetchModule.mockResolvedValue({
      key: 'speaking',
      dims: { pron: 77.5, flu: 70, gram: 68.2 },
      trend: [{ date: '2026-09-20', pron: 70, flu: 60, gram: 65 }],
      weak_phonemes: [{ phoneme: 'th', count: 3, avg: 55 }],
    })
    const wrapper = await mountAt('speaking')
    expect(mocks.fetchModule).toHaveBeenCalledWith('speaking')
    expect(wrapper.text()).toContain('77.5')
    expect(wrapper.text()).toContain('/th/ · 3 次')
    expect(wrapper.findAll('.u-learn-detail__pr').length).toBe(1)
  })

  it('speaking：无数据时展示空态而非演示帧', async () => {
    mocks.fetchModule.mockResolvedValue({ key: 'speaking', dims: { pron: null, flu: null, gram: null }, trend: [], weak_phonemes: [] })
    const wrapper = await mountAt('speaking')
    expect(wrapper.text()).toContain('还没有练习记录')
    expect(wrapper.text()).toContain('暂无薄弱音素记录')
    expect(wrapper.findAll('.u-learn-detail__pr').length).toBe(0)
  })

  it('practice：渲染会话分布 + 剧本回合进度 + 热力图', async () => {
    mocks.fetchModule.mockResolvedValue({
      key: 'practice',
      minutes: 86,
      by_kind: [{ kind: 'sing', count: 3, minutes: 86 }],
      campaigns: [{ id: 1, name: '迷雾酒馆', turns: 10, user_turns: 4, last_active_at: null }],
      heatmap: [{ date: '2026-09-21', count: 12, level: 3 }],
    })
    const wrapper = await mountAt('practice')
    expect(wrapper.text()).toContain('共 86 分钟 · 3 次会话')
    expect(wrapper.text()).toContain('唱吧跟唱 · 3 次')
    expect(wrapper.text()).toContain('迷雾酒馆')
    expect(wrapper.text()).toContain('4/10')
    expect(wrapper.findAll('.u-learn-heat__cell').length).toBe(84)
  })

  it('words：渲染生词状态与词典首义，未收录词回退来源元信息', async () => {
    mocks.fetchModule.mockResolvedValue({
      key: 'words',
      items: [
        { word: 'coffee', status: 'learning', scene: 'reading', created_at: '2026-09-20T10:00:00+00:00', translation: 'n. 咖啡', phonetic: 'ˈkɔːfi' },
        { word: 'lighthouse', status: 'new', scene: 'reading', created_at: '2026-09-19T10:00:00+00:00', translation: null },
      ],
    })
    const wrapper = await mountAt('words')
    expect(wrapper.text()).toContain('n. 咖啡')
    expect(wrapper.text()).toContain('学习中')
    expect(wrapper.text()).toContain('新词')
    expect(wrapper.text()).toContain('阅读 · 2026-09-19')
  })

  it('community：渲染常逛页面与互动类型统计', async () => {
    mocks.fetchModule.mockResolvedValue({
      key: 'community',
      trend: [{ date: '2026-09-21', count: 5 }],
      pages: [{ page: '/m/home', count: 4 }],
      events: [{ event_type: 'word_lookup', count: 2 }],
    })
    const wrapper = await mountAt('community')
    expect(wrapper.text()).toContain('首页')
    expect(wrapper.text()).toContain('划词查词')
    expect(wrapper.text()).toContain('共 5 次')
  })

  it('接口失败：显示错误与重试（可重新拉取）', async () => {
    mocks.fetchModule.mockRejectedValueOnce(new Error('net down'))
    const wrapper = await mountAt('practice')
    expect(wrapper.text()).toContain('加载失败')
    expect(wrapper.text()).toContain('net down')

    mocks.fetchModule.mockResolvedValueOnce({ key: 'practice', minutes: 0, by_kind: [], campaigns: [], heatmap: [] })
    await wrapper.get('.u-comm-empty__btn').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('近 30 天还没有练习会话')
  })
})
