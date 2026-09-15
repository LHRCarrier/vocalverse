/**
 * 我的资料页（社区 S3 · docs/47 §5.1 · /m/me/profile）
 *
 * 2026-09-14 组长手机实测：在资料页改了头像 + 昵称 → **回社区列表卡片仍是旧头像/旧昵称**，
 * 点进帖子详情才看到新的（同一屏里顶栏已是新头像）。根因：社区 feed store 按 domain 缓存
 * 作者快照，`load()` 命中缓存就不发请求，而改资料发生在另一个页面。
 *
 * 本用例锁「保存成功 → 社区 feed（当前列表 + domain 缓存）里的本人作者快照立即是新值」——
 * 修复前必失败（`applyMyProfile` 未接线时 items 仍是旧昵称）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileMediaPicker from '@/components/mobile/MobileMediaPicker.vue'
import MobileProfileView from '@/views/mobile/MobileProfileView.vue'
import { useAuthStore } from '@/stores/auth'
import { useCommunityStore } from '@/stores/community'

import type { CommunityPostView } from '@/types/community'

const api = vi.hoisted(() => ({ patchMe: vi.fn(), fetchFeed: vi.fn() }))

vi.mock('@/api/users', () => ({ patchMe: (...a: unknown[]) => api.patchMe(...a) }))
vi.mock('@/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/community')>()
  return { ...actual, fetchFeed: (...a: unknown[]) => api.fetchFeed(...a) }
})

/** 改资料前 `GET /auth/me` 的回包（昵称旧、无头像） */
const beforeEdit = {
  userId: 7,
  username: 'lhr',
  nickname: '成年中级',
  level: 'L3',
  handle: 'demo_adult',
  tint: '#16303a',
  avatarUrl: null,
}

/** 保存后 `PATCH /api/v1/users/me` 的回包（服务端真值） */
const afterEdit = {
  ...beforeEdit,
  nickname: '林浩然',
  handle: 'lin',
  avatarUrl: '/api/v1/media/new-avatar',
}

/** 社区首页已拉过的那条本人帖（作者快照 = 改资料前的旧值） */
const myPost = {
  id: 5,
  author: { id: 7, nickname: '成年中级', handle: 'demo_adult', tint: '#16303a', level: 'L3', avatarUrl: null },
  kind: 'article',
  domain: 'teaching',
  title: '今日打卡',
  body: '完成 5 次口语练习',
  media: null,
  createdAt: '2026-09-14T09:00:00Z',
  likeCount: 0,
  coinCount: 0,
  commentCount: 0,
  shareCount: 0,
  liked: false,
  coined: false,
  checkinOverall: null,
  checkinPracticeCount: null,
  checkinDate: null,
} as unknown as CommunityPostView

function envelope(data: unknown) {
  return { ok: true, status: 200, json: async () => ({ code: 0, message: 'ok', data }) } as unknown as Response
}

const fetchMock = vi.fn()

async function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.token = 'test-token' // fetchMe 无 token 直接 return
  const community = useCommunityStore()
  // 社区首页先拉过一次流：旧作者快照进了 items + domain 缓存
  api.fetchFeed.mockResolvedValue({ items: [myPost], nextCursor: null, hasMore: false })
  await community.load(null)

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/m/me/profile', component: MobileProfileView },
      { path: '/m/home', component: { template: '<div />' } },
      { path: '/m/me/posts', component: { template: '<div />' } },
    ],
  })
  await router.push('/m/me/profile')
  await router.isReady()
  const wrapper = mount(MobileProfileView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, community, auth }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('我的资料（改头像/昵称后社区列表即时刷新）', () => {
  beforeEach(() => {
    api.patchMe.mockReset().mockResolvedValue(afterEdit)
    api.fetchFeed.mockReset()
    fetchMock.mockReset()
    // 挂载时 fetchMe → 旧资料；保存后 fetchMe → 新资料
    fetchMock.mockResolvedValueOnce(envelope(beforeEdit)).mockResolvedValue(envelope(afterEdit))
    vi.stubGlobal('fetch', fetchMock)
  })

  it('保存成功 → 社区列表与缓存里的本人作者快照立即更新（修复前仍是旧昵称/旧头像）', async () => {
    const { wrapper, community, auth } = await mountView()

    // 改资料前：社区卡片是旧快照
    expect(community.items[0].author.nickname).toBe('成年中级')
    expect(community.items[0].author.avatarUrl).toBeNull()
    expect(auth.me?.nickname).toBe('成年中级')

    // 换头像（媒体选择器回调）+ 改昵称/@handle
    wrapper.findComponent(MobileMediaPicker).vm.$emit('update:selected', [{ url: afterEdit.avatarUrl }])
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('林浩然')
    await inputs[1].setValue('lin')
    await wrapper.get('.u-btn--primary').trigger('click')
    await flushPromises()

    expect(api.patchMe).toHaveBeenCalledWith({
      nickname: '林浩然',
      handle: 'lin',
      avatarUrl: '/api/v1/media/new-avatar',
    })

    // 社区列表（store.items）立即是新资料
    expect(community.items[0].author.nickname).toBe('林浩然')
    expect(community.items[0].author.handle).toBe('lin')
    expect(community.items[0].author.avatarUrl).toBe('/api/v1/media/new-avatar')

    // 返回社区首页：命中 domain 缓存（不再发请求）也不回退成旧快照
    await community.load(null)
    expect(api.fetchFeed).toHaveBeenCalledTimes(1)
    expect(community.items[0].author.nickname).toBe('林浩然')
    expect(community.items[0].author.avatarUrl).toBe('/api/v1/media/new-avatar')

    // 顶栏/抽屉走的 auth.me 也是新的
    expect(auth.me?.nickname).toBe('林浩然')
  })
})
