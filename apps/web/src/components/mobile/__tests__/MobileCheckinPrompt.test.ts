import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileCheckinPrompt from '@/components/mobile/MobileCheckinPrompt.vue'
import { useAuthStore } from '@/stores/auth'
import { localDateKey } from '@/stores/checkin'

import type { CommunityPostView } from '@/types/community'

const mocks = vi.hoisted(() => ({
  fetchFeed: {} as ReturnType<typeof vi.fn>,
}))

vi.mock('@/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/community')>()
  mocks.fetchFeed = vi.fn()
  return { ...actual, fetchFeed: mocks.fetchFeed }
})

vi.mock('@/api/checkin', () => ({ manualCheckin: vi.fn() }))

function checkinPost(id: number, date: string): CommunityPostView {
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
    checkinOverall: 80,
    checkinPracticeCount: 1,
    checkinDate: date,
  }
}

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/home', component: { template: '<div/>' } },
    { path: '/m/checkin', component: { template: '<div/>' } },
  ],
})

let pinia: ReturnType<typeof createPinia>

async function mountPrompt() {
  await router.push('/m/home')
  await router.isReady()
  const wrapper = mount(MobileCheckinPrompt, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return wrapper
}

describe('MobileCheckinPrompt（今日首次进入 · 侧边提示）', () => {
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    localStorage.clear()
    mocks.fetchFeed.mockReset()
  })

  it('已登录 + 今日未打卡 + 当天未提示过 → 出现提示', async () => {
    useAuthStore().me = { userId: 1, username: 'demo', nickname: '我', level: 'L3' }
    mocks.fetchFeed.mockResolvedValue({ items: [], nextCursor: null, hasMore: false })

    const wrapper = await mountPrompt()

    expect(wrapper.find('.u-checkin-prompt').exists()).toBe(true)
    expect(wrapper.text()).toContain('今日还没打卡')
    expect(localStorage.getItem('vv.checkin.prompt.date')).toBe(localDateKey())
  })

  it('今日已打卡 → 不提示', async () => {
    useAuthStore().me = { userId: 1, username: 'demo', nickname: '我', level: 'L3' }
    mocks.fetchFeed.mockResolvedValue({
      items: [checkinPost(1, localDateKey())],
      nextCursor: null,
      hasMore: false,
    })

    const wrapper = await mountPrompt()

    expect(wrapper.find('.u-checkin-prompt').exists()).toBe(false)
  })

  it('当天已提示过（localStorage 记录）→ 不再重复打扰', async () => {
    useAuthStore().me = { userId: 1, username: 'demo', nickname: '我', level: 'L3' }
    localStorage.setItem('vv.checkin.prompt.date', localDateKey())
    mocks.fetchFeed.mockResolvedValue({ items: [], nextCursor: null, hasMore: false })

    const wrapper = await mountPrompt()

    expect(wrapper.find('.u-checkin-prompt').exists()).toBe(false)
  })

  it('未登录 → 不提示', async () => {
    mocks.fetchFeed.mockResolvedValue({ items: [], nextCursor: null, hasMore: false })
    const wrapper = await mountPrompt()
    expect(wrapper.find('.u-checkin-prompt').exists()).toBe(false)
  })

  it('点提示 → 跳转打卡页', async () => {
    useAuthStore().me = { userId: 1, username: 'demo', nickname: '我', level: 'L3' }
    mocks.fetchFeed.mockResolvedValue({ items: [], nextCursor: null, hasMore: false })

    const wrapper = await mountPrompt()
    await wrapper.find('.u-checkin-prompt__go').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/m/checkin')
  })
})
