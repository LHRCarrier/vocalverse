import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { localDateKey } from '@/stores/checkin'
import MobileCheckinView from '@/views/mobile/MobileCheckinView.vue'

import type { CommunityPostView } from '@/types/community'

const mocks = vi.hoisted(() => ({
  fetchFeed: {} as ReturnType<typeof vi.fn>,
  manualCheckin: {} as ReturnType<typeof vi.fn>,
}))

vi.mock('@/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/community')>()
  mocks.fetchFeed = vi.fn()
  return { ...actual, fetchFeed: mocks.fetchFeed }
})

vi.mock('@/api/checkin', () => {
  mocks.manualCheckin = vi.fn()
  return { manualCheckin: mocks.manualCheckin }
})

function checkinPost(id: number, date: string, count = 1, overall: number | null = 80): CommunityPostView {
  return {
    id,
    author: { id: 1, nickname: '我', handle: 'me', tint: null, level: 'L3', avatarUrl: null },
    kind: 'checkin',
    domain: null,
    title: '今日打卡',
    body: null,
    media: null,
    createdAt: `${date}T10:00:00.000Z`,
    likeCount: 0,
    coinCount: 0,
    commentCount: 0,
    shareCount: 0,
    liked: false,
    coined: false,
    checkinOverall: overall,
    checkinPracticeCount: count,
    checkinDate: date,
  }
}

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/checkin', component: MobileCheckinView },
    { path: '/m/learn', component: { template: '<div/>' } },
    { path: '/m/post/:postId', component: { template: '<div/>' } },
  ],
})

async function mountView() {
  await router.push('/m/checkin')
  await router.isReady()
  return mount(MobileCheckinView, {
    global: {
      plugins: [createPinia(), router],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
}

describe('MobileCheckinView（打卡页）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mocks.fetchFeed.mockReset()
    mocks.manualCheckin.mockReset()
  })

  it('未打卡：状态/连续天数/按钮可点，历史为空态', async () => {
    mocks.fetchFeed.mockResolvedValue({ items: [], nextCursor: null, hasMore: false })
    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('今天还没打卡')
    expect(wrapper.text()).toContain('连续')
    expect(wrapper.text()).toContain('还没有打卡记录')
    const btn = wrapper.find('.u-checkin-hero__btn')
    expect(btn.attributes('disabled')).toBeUndefined()
    expect(btn.text()).toBe('打卡')
  })

  it('已打卡：状态 + 按钮禁用 + 历史记录（次数/分数）', async () => {
    const today = localDateKey()
    mocks.fetchFeed.mockResolvedValue({
      items: [checkinPost(9, today, 3, 88)],
      nextCursor: null,
      hasMore: false,
    })
    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('今日已打卡')
    expect(wrapper.find('.u-checkin-hero__btn').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.u-checkin-row').text()).toContain('3 次练习')
    expect(wrapper.find('.u-checkin-row').text()).toContain('88')
  })

  it('点打卡：调接口 → 状态翻为已打卡（手动触发，不由练习自动生成）', async () => {
    const today = localDateKey()
    mocks.fetchFeed.mockResolvedValueOnce({ items: [], nextCursor: null, hasMore: false })
    mocks.manualCheckin.mockResolvedValue({ date: today, practiceCount: 1, overall: 90 })
    mocks.fetchFeed.mockResolvedValue({
      items: [checkinPost(10, today, 1, 90)],
      nextCursor: null,
      hasMore: false,
    })

    const wrapper = await mountView()
    await flushPromises()
    await wrapper.find('.u-checkin-hero__btn').trigger('click')
    await flushPromises()

    expect(mocks.manualCheckin).toHaveBeenCalledWith(today)
    expect(wrapper.text()).toContain('今日已打卡')
  })
})
