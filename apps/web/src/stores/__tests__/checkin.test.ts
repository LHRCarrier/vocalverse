import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { computeStreak, localDateKey, useCheckinStore } from '@/stores/checkin'
import { useUiStore } from '@/stores/ui'

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

function feedOf(items: CommunityPostView[]) {
  return { items, nextCursor: null, hasMore: false }
}

describe('checkin store（手动打卡 · 2026-09-21 改版）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mocks.fetchFeed.mockReset()
    mocks.manualCheckin.mockReset()
  })

  it('localDateKey 用本地日期（不走 UTC，避免凌晨算成昨天）', () => {
    expect(localDateKey(new Date(2026, 8, 21, 0, 30))).toBe('2026-09-21')
    expect(localDateKey(new Date(2026, 11, 1, 23, 59))).toBe('2026-12-01')
  })

  it('computeStreak：今天已打卡从今天数；今天没打卡从昨天数；断档归零', () => {
    const today = '2026-09-21'
    expect(computeStreak(['2026-09-21', '2026-09-20', '2026-09-19'], today)).toBe(3)
    expect(computeStreak(['2026-09-20', '2026-09-19'], today)).toBe(2) // 今天还没打，连续未断
    expect(computeStreak(['2026-09-19'], today)).toBe(0) // 昨天缺 → 断档
    expect(computeStreak([], today)).toBe(0)
  })

  it('refresh：从我的打卡卡算今日状态与连续天数（不写死演示值）', async () => {
    mocks.fetchFeed.mockResolvedValue(
      feedOf([checkinPost(3, localDateKey()), checkinPost(2, '2026-09-20')]),
    )
    const store = useCheckinStore()
    await store.refresh()

    expect(store.checkedIn).toBe(true)
    expect(store.streak).toBe(2)
    expect(store.cards).toHaveLength(2)
    // mine=true 只取本人内容（不看他人帖子）
    expect(mocks.fetchFeed).toHaveBeenCalledWith(null, null, 30, undefined, true)
  })

  it('refresh 失败：不误报「未打卡」（failed 标记，提示组件据此隐藏）', async () => {
    mocks.fetchFeed.mockRejectedValue(new Error('offline'))
    const store = useCheckinStore()
    await store.refresh()

    expect(store.loaded).toBe(false)
    expect(store.failed).toBe(true)
    expect(store.checkedIn).toBe(false)
  })

  it('checkIn：带本地日期调接口 → 重拉状态 → 成功 toast', async () => {
    const today = localDateKey()
    mocks.manualCheckin.mockResolvedValue({ date: today, practiceCount: 2, overall: 88 })
    mocks.fetchFeed.mockResolvedValue(feedOf([checkinPost(9, today, 2, 88)]))

    const store = useCheckinStore()
    const ok = await store.checkIn()

    expect(ok).toBe(true)
    expect(mocks.manualCheckin).toHaveBeenCalledWith(today)
    expect(store.checkedIn).toBe(true)
    expect(useUiStore().toastText).toContain('88')
  })

  it('checkIn 失败：返回 false + 失败 toast + 不卡 submitting', async () => {
    mocks.manualCheckin.mockRejectedValue(new Error('打卡失败，请稍后重试'))
    const store = useCheckinStore()
    const ok = await store.checkIn()

    expect(ok).toBe(false)
    expect(store.submitting).toBe(false)
    expect(useUiStore().toastText).toContain('打卡失败')
  })
})
