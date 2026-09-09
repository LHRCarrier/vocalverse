/**
 * 我的发帖页（社区 S3 · 2026-09-09 组长实测补）
 *
 * 锁三件事：
 * 1. 走服务端作者过滤（`fetchFeed(..., mine=true)`），不是前端过滤当前页；
 * 2. 空态给「去发帖」入口（发完帖有地方回看）；
 * 3. 列表内删除 → 调 deletePost 并从列表移除。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileMyPostsView from '@/views/mobile/MobileMyPostsView.vue'

const api = vi.hoisted(() => ({
  fetchFeed: vi.fn(),
  deletePost: vi.fn(),
}))

vi.mock('@/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/community')>()
  return {
    ...actual,
    fetchFeed: (...a: unknown[]) => api.fetchFeed(...a),
    deletePost: (...a: unknown[]) => api.deletePost(...a),
  }
})

const mine = {
  id: 99,
  author: { id: 1, nickname: 'Emma', handle: 'emmaenglish', tint: '#1e2b26', level: 'L3', avatarUrl: null },
  kind: 'article',
  domain: 'teaching',
  title: '我发的第一条',
  body: 'hello',
  media: null,
  createdAt: '2026-09-09T03:00:00Z',
  likeCount: 0,
  coinCount: 0,
  commentCount: 0,
  shareCount: 0,
  liked: false,
  coined: false,
  checkinOverall: null,
  checkinPracticeCount: null,
  checkinDate: null,
}

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/m/me/posts', component: MobileMyPostsView },
      { path: '/m/home', component: { template: '<div />' } },
      { path: '/m/compose', component: { template: '<div />' } },
      { path: '/m/post/:postId', component: { template: '<div />' } },
    ],
  })
  await router.push('/m/me/posts')
  await router.isReady()
  const wrapper = mount(MobileMyPostsView, { global: { plugins: [router, createPinia()] } })
  await flushPromises()
  return { wrapper, router }
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('我的发帖', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.fetchFeed.mockReset().mockResolvedValue({ items: [mine], nextCursor: null, hasMore: false })
    api.deletePost.mockReset().mockResolvedValue(undefined)
  })

  it('用服务端作者过滤（mine=true），渲染我的帖子', async () => {
    const { wrapper } = await mountView()
    expect(api.fetchFeed).toHaveBeenCalledWith(null, null, 10, undefined, true)
    expect(wrapper.text()).toContain('我发的第一条')
    expect(wrapper.text()).toContain('我的发帖')
  })

  it('空态：给「去发帖」入口', async () => {
    api.fetchFeed.mockResolvedValue({ items: [], nextCursor: null, hasMore: false })
    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain('还没有发过内容')
    expect(wrapper.text()).toContain('去发帖')
  })

  it('列表内删除：调 deletePost 并从列表移除', async () => {
    const { wrapper } = await mountView()
    await wrapper.get('button[aria-label^="删除"]').trigger('click')
    await flushPromises()
    expect(api.deletePost).toHaveBeenCalledWith(99)
    expect(wrapper.text()).not.toContain('我发的第一条')
  })

  it('加载失败：可重试', async () => {
    api.fetchFeed.mockRejectedValueOnce(new Error('服务不可达'))
    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain('加载失败')
    expect(wrapper.text()).toContain('服务不可达')
  })
})
