import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileNotificationsView from '@/views/mobile/MobileNotificationsView.vue'

const mocks = vi.hoisted(() => ({
  fetchNotifications: {} as ReturnType<typeof vi.fn>,
  fetchFollows: {} as ReturnType<typeof vi.fn>,
  fetchFollowRecommendations: {} as ReturnType<typeof vi.fn>,
  fetchFollowingFeed: {} as ReturnType<typeof vi.fn>,
  followUser: {} as ReturnType<typeof vi.fn>,
  unfollowUser: {} as ReturnType<typeof vi.fn>,
}))

vi.mock('@/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/community')>()
  const now = new Date().toISOString()
  mocks.fetchNotifications = vi.fn().mockResolvedValue({
    items: [
      { id: 'n|1', type: 'like', postId: 1, postTitle: 'S2 帖', actorNickname: '张三', actorCount: 2, commentBody: null, createdAt: now },
      { id: 'c|2', type: 'comment', postId: 1, postTitle: 'S2 帖', actorNickname: '李四', actorCount: 1, commentBody: '好帖', createdAt: now },
    ],
    nextCursor: null,
    hasMore: false,
  })
  mocks.fetchFollows = vi.fn().mockResolvedValue([
    { author: { id: 2, nickname: 'Teacher Amy', handle: 'amyteach', tint: null, level: 'L3' }, followedAt: now, youFollowBack: false },
  ])
  mocks.fetchFollowRecommendations = vi.fn().mockResolvedValue([
    { author: { id: 2, nickname: 'Teacher Amy', handle: 'amyteach', tint: null, level: 'L3' }, followed: true },
    { author: { id: 3, nickname: 'Emma English', handle: 'emmaenglish', tint: null, level: 'L3' }, followed: false },
  ])
  mocks.fetchFollowingFeed = vi.fn().mockResolvedValue({
    items: [
      {
        id: 9,
        author: { id: 2, nickname: 'Teacher Amy', handle: 'amyteach', tint: null, level: 'L3' },
        kind: 'article', domain: 'news', title: 'New post from Amy', body: null, media: null,
        createdAt: now, likeCount: 88, coinCount: 1, commentCount: 2, shareCount: 0,
        liked: false, coined: false, checkinOverall: null, checkinPracticeCount: null, checkinDate: null,
      },
    ],
    nextCursor: null,
    hasMore: false,
  })
  mocks.followUser = vi.fn().mockResolvedValue({ data: null })
  mocks.unfollowUser = vi.fn().mockResolvedValue({ data: null })
  return {
    ...actual,
    fetchNotifications: mocks.fetchNotifications,
    fetchFollows: mocks.fetchFollows,
    fetchFollowRecommendations: mocks.fetchFollowRecommendations,
    fetchFollowingFeed: mocks.fetchFollowingFeed,
    followUser: mocks.followUser,
    unfollowUser: mocks.unfollowUser,
  }
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/m/notifications', component: MobileNotificationsView }],
})

function mountView() {
  return mount(MobileNotificationsView, {
    global: {
      plugins: [createPinia(), router],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  for (const k of Object.keys(mocks)) mocks[k as keyof typeof mocks]?.mockClear?.()
})

describe('MobileNotificationsView（S2 真实化）', () => {
  it('私信 tab（默认）：演示会话列表仍渲染', async () => {
    const wrapper = mountView()
    expect(wrapper.text()).toContain('Kai')
    expect(wrapper.text()).toContain('Momo')
  })

  it('通知 tab：mergeKey 聚合文案（张三 等 2 人…）+ 评论逐条带内容', async () => {
    const wrapper = mountView()
    await wrapper.findAll('button.u-notif-tab')[1].trigger('click') // 第 2 个 tab = 通知
    await flushPromises()

    const text = wrapper.text()
    expect(mocks.fetchNotifications).toHaveBeenCalledTimes(1)
    expect(text).toContain('张三 等 2 人')
    expect(text).toContain('赞了你的内容《S2 帖》')
    expect(text).toContain('李四')
    expect(text).toContain('好帖')
  })

  it('关注 tab：推荐关注（已关注/未关注标记）+ 关注流渲染；点关注按钮调接口并重新加载', async () => {
    const wrapper = mountView()
    await wrapper.findAll('button.u-notif-tab')[2].trigger('click') // 第 3 个 tab = 关注
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('推荐关注')
    expect(text).toContain('Teacher Amy')
    expect(text).toContain('Emma English')
    expect(text).toContain('New post from Amy')
    expect(text).toContain('88')

    // 点击未关注作者（Emma English → 关注）
    const followBtn = wrapper
      .findAll('button.u-notif-follow-btn')
      .find((b) => b.text() === '关注')
    expect(followBtn).toBeTruthy()
    await followBtn!.trigger('click')
    await flushPromises()
    expect(mocks.followUser).toHaveBeenCalledWith(3)
    expect(mocks.fetchFollowRecommendations).toHaveBeenCalledTimes(2) // 初始 + 操作后 reload
  })

  it('?tab= 参数直达对应 tab（抽屉通知下拉子项 · S2 真实流）', async () => {
    await router.push('/m/notifications?tab=follow')
    await router.isReady()
    const wrapper = mount(MobileNotificationsView, {
      global: {
        plugins: [createPinia(), router],
        stubs: { RouterLink: { template: '<a><slot /></a>' } },
      },
    })
    await flushPromises()
    expect(mocks.fetchFollowRecommendations).toHaveBeenCalled() // 直达关注 tab 即拉取
    expect(wrapper.findAll('.u-notif-tab')[2].classes()).toContain('active')
    expect(wrapper.text()).toContain('推荐关注')
  })
})
