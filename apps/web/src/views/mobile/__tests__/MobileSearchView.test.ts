/**
 * 搜索页接真（docs/53 P5 ①）：三 tab 走 Python `/api/v1/search`（帖子/用户/教程），
 * 250ms 防抖 + 空态/失败态；最近搜索为本地真实历史。
 */
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileSearchView from '@/views/mobile/MobileSearchView.vue'

const mocks = vi.hoisted(() => ({
  searchPosts: vi.fn(),
  searchUsers: vi.fn(),
  searchTutorials: vi.fn(),
}))

vi.mock('@/api/search', () => ({
  searchPosts: mocks.searchPosts,
  searchUsers: mocks.searchUsers,
  searchTutorials: mocks.searchTutorials,
}))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/search', component: MobileSearchView },
    { path: '/m/post/:postId', component: { template: '<div/>' } },
  ],
})

async function mountView() {
  await router.push('/m/search')
  await router.isReady()
  const wrapper = mount(MobileSearchView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

/** 输入 → 跳过 250ms 防抖 → 等请求完成 */
async function type(wrapper: Awaited<ReturnType<typeof mountView>>, text: string) {
  await wrapper.get('input[aria-label="搜索关键词"]').setValue(text)
  await vi.advanceTimersByTimeAsync(300)
  await flushPromises()
}

enableAutoUnmount(afterEach)

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  vi.useFakeTimers()
  localStorage.clear()
})

afterEach(() => {
  vi.useRealTimers()
  localStorage.clear()
})

describe('MobileSearchView（docs/53 P5 接真）', () => {
  it('空关键词：显示本地搜索历史与热门话题', async () => {
    localStorage.setItem('vv_search_history', JSON.stringify(['phrasal verbs']))
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('最近搜索')
    expect(wrapper.text()).toContain('phrasal verbs')
    expect(wrapper.text()).toContain('热门话题')
    expect(wrapper.text()).toContain('#Shadowing')
  })

  it('输入关键词 → 防抖后请求帖子接口并渲染结果；点击跳详情', async () => {
    mocks.searchPosts.mockResolvedValue([
      {
        id: 7,
        title: "Inside China's English learning boom",
        domain: 'news',
        kind: 'article',
        author: { nickname: 'Teacher Amy', handle: 'amyteach', tint: '#37546e', avatar_url: null },
        created_at: null,
      },
    ])
    const wrapper = await mountView()
    await type(wrapper, 'english')
    expect(mocks.searchPosts).toHaveBeenCalledWith('english')
    expect(wrapper.text()).toContain('Teacher Amy')
    expect(wrapper.text()).toContain('英语新闻')

    await wrapper.get('button.u-search__row').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/m/post/7')
  })

  it('切换分类：用户 tab 请求用户接口；无结果走空态', async () => {
    mocks.searchPosts.mockResolvedValue([])
    mocks.searchUsers.mockResolvedValue([
      { user_id: 2, nickname: 'Kai', handle: 'kai_learns', tint: '#16303a', avatar_url: null, cefr_level: 'L3' },
    ])
    const wrapper = await mountView()
    await type(wrapper, 'kai')
    expect(wrapper.text()).toContain('没找到相关内容')

    await wrapper.findAll('.u-x-tab')[1].trigger('click')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()
    expect(mocks.searchUsers).toHaveBeenCalledWith('kai')
    expect(wrapper.text()).toContain('@kai_learns')
  })

  it('教程 tab：渲染听力素材等级与来源', async () => {
    mocks.searchPosts.mockResolvedValue([])
    mocks.searchTutorials.mockResolvedValue([
      { id: 1, title: 'Shadowing tutorial · 10 minutes', level: 1, duration_s: 600, source: 'public_domain', tags: ['口语'] },
    ])
    const wrapper = await mountView()
    await type(wrapper, 'shadow')
    await wrapper.findAll('.u-x-tab')[2].trigger('click')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()
    expect(wrapper.text()).toContain('Shadowing tutorial · 10 minutes')
    expect(wrapper.text()).toContain('Lv1')
    expect(wrapper.text()).toContain('公有领域')
  })

  it('接口失败：显示错误态（不假装空结果）', async () => {
    mocks.searchPosts.mockRejectedValue(new Error('net down'))
    const wrapper = await mountView()
    await type(wrapper, 'english')
    expect(wrapper.text()).toContain('搜索失败')
    expect(wrapper.text()).toContain('net down')
  })
})
