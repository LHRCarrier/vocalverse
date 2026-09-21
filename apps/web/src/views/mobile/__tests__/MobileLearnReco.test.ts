/**
 * 学习页「为你推荐」卡（docs/53 P3）：真实推荐流渲染 + 点击上报 recommend_click + 跳转。
 * 曝光由服务端在 /api/v1/recommendations?type=items 返回时落库，前端不重复上报。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileLearnView from '@/views/mobile/MobileLearnView.vue'

const mocks = vi.hoisted(() => ({
  fetchItems: vi.fn(),
  track: vi.fn(),
  refreshCheckin: vi.fn(),
  fetchLearn: vi.fn(),
}))

vi.mock('@/api/reco', () => ({ fetchItemsRecommendations: mocks.fetchItems }))
vi.mock('@/api/events', () => ({ track: mocks.track }))
vi.mock('@/api/stats', () => ({
  fetchLearnOverview: mocks.fetchLearn,
}))
vi.mock('@/stores/checkin', () => ({
  useCheckinStore: () => ({ streak: 0, refresh: mocks.refreshCheckin }),
}))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/learn', component: MobileLearnView },
    { path: '/m/sing', component: { template: '<div/>' } },
    { path: '/m/books/:bookId', component: { template: '<div/>' } },
    { path: '/m/tavern', component: { template: '<div/>' } },
    { path: '/m/vocab', component: { template: '<div/>' } },
    { path: '/m/bookshelf', component: { template: '<div/>' } },
    { path: '/m/learn/:module', component: { template: '<div/>' } },
  ],
})

async function mountView() {
  await router.push('/m/learn')
  await router.isReady()
  const wrapper = mount(MobileLearnView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  mocks.fetchLearn.mockResolvedValue({
    profile_line: '近 30 天练了 2 次',
    heatmap: [],
    modules: {
      words: { summary: 'w' },
      community: { summary: 'c' },
      speaking: { summary: 's' },
      practice: { summary: 'p' },
    },
    generated_at: '2026-09-21T00:00:00+00:00',
  })
})

describe('学习页 · 为你推荐（docs/53 P3）', () => {
  it('渲染推荐条目（标题/品类/理由）', async () => {
    mocks.fetchItems.mockResolvedValue({
      items: [
        { kind: 'song', id: 1, title: 'Space Song', subtitle: 'A', level: 'L3', score: 0.9, reason: '匹配 L3' },
        { kind: 'book', id: 2, title: 'Space Odyssey', subtitle: 'C', level: 'L3', score: 0.8, reason: '命中兴趣' },
      ],
      level: 'L3',
      rule_version: 'items-content-v1',
      recommend_group_id: 'grp-1',
    })
    const wrapper = await mountView()
    const text = wrapper.text()
    expect(text).toContain('为你推荐')
    expect(text).toContain('Space Song')
    expect(text).toContain('读物')
    expect(text).toContain('命中兴趣')
  })

  it('点击条目 → 上报 recommend_click（带推荐组 id）并跳转对应页面', async () => {
    mocks.fetchItems.mockResolvedValue({
      items: [
        { kind: 'book', id: 42, title: 'Space Odyssey', subtitle: 'C', level: 'L3', score: 0.8, reason: '命中兴趣' },
      ],
      level: 'L3',
      rule_version: 'items-content-v1',
      recommend_group_id: 'grp-42',
    })
    const wrapper = await mountView()
    await wrapper.get('.u-learn-reco__row').trigger('click')
    await flushPromises()

    expect(mocks.track).toHaveBeenCalledWith(
      'recommend_click',
      expect.objectContaining({ recommendGroupId: 'grp-42', targetType: 'book', targetId: 42 }),
    )
    expect(router.currentRoute.value.path).toBe('/m/books/42')
  })

  it('推荐接口失败 → 卡片不渲染且不抛错（非关键路径）', async () => {
    mocks.fetchItems.mockRejectedValue(new Error('net down'))
    const wrapper = await mountView()
    expect(wrapper.find('.u-learn-reco').exists()).toBe(false)
  })
})
