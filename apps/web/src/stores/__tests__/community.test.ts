import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useCommunityStore } from '@/stores/community'
import * as communityApi from '@/api/community'

import type { CommunityPostView, FeedPage } from '@/types/community'

vi.mock('@/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/community')>()
  return { ...actual, fetchFeed: vi.fn() }
})

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const post = (id: number) => ({ id }) as unknown as CommunityPostView
const page = (items: CommunityPostView[], nextCursor: string | null, hasMore: boolean): FeedPage => ({
  items,
  nextCursor,
  hasMore,
})

describe('community store（fe-03 竞态守卫 + fe-04 上限裁剪）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(communityApi.fetchFeed).mockReset()
  })

  it('旧请求不覆盖新 domain（修复前失败：慢的 news 响应晚到覆盖 overseas）', async () => {
    const store = useCommunityStore()
    const dNews = deferred<FeedPage>()
    const dOverseas = deferred<FeedPage>()
    vi.mocked(communityApi.fetchFeed).mockImplementation((domain) => {
      if (domain === 'news') return dNews.promise
      return dOverseas.promise
    })

    const pNews = store.load('news')
    const pOverseas = store.load('overseas')

    // overseas 先返回
    dOverseas.resolve(page([post(2)], 'c2', false))
    await pOverseas
    expect(store.activeDomain).toBe('overseas')
    expect(store.items.map((i) => i.id)).toEqual([2])

    // 慢的 news 后到：修复前会覆盖成 news 内容（items=[1]），修复后被 seq 守卫丢弃
    dNews.resolve(page([post(1)], 'c1', false))
    await pNews
    expect(store.items.map((i) => i.id)).toEqual([2])
  })

  it('切 Tab 时 abort 上一次 in-flight load', async () => {
    const store = useCommunityStore()
    const signals: AbortSignal[] = []
    vi.mocked(communityApi.fetchFeed).mockImplementation((_domain, _cursor, _limit, signal) => {
      signals.push(signal!)
      return deferred<FeedPage>().promise
    })
    void store.load('news')
    void store.load('overseas')
    // 第二次 load 触发 abort 第一次的 signal（修复前：无 controller，永不 abort）
    expect(signals[0]?.aborted).toBe(true)
    expect(signals[1]?.aborted).toBe(false)
  })

  it('按 domain 缓存：切回已加载领域免走网络', async () => {
    const store = useCommunityStore()
    vi.mocked(communityApi.fetchFeed).mockResolvedValue(page([post(1)], 'c1', false))

    await store.load('news')
    expect(store.items.map((i) => i.id)).toEqual([1])
    expect(vi.mocked(communityApi.fetchFeed)).toHaveBeenCalledTimes(1)

    // 切回 news：命中缓存，不触发网络
    await store.load('news')
    expect(vi.mocked(communityApi.fetchFeed)).toHaveBeenCalledTimes(1)
    expect(store.items.map((i) => i.id)).toEqual([1])

    // force（下拉刷新）绕过缓存
    await store.load('news', { force: true })
    expect(vi.mocked(communityApi.fetchFeed)).toHaveBeenCalledTimes(2)
  })

  it('loadMore 超过上限裁剪（fe-04：防长列表无界增长）', async () => {
    const store = useCommunityStore()
    vi.mocked(communityApi.fetchFeed).mockResolvedValueOnce(
      page(Array.from({ length: 10 }, (_, i) => post(i + 1)), 'c1', true),
    )
    await store.load('news')
    expect(store.items).toHaveLength(10)

    // 追加 60 条 → 总数 70 > LIST_CAP(60) → 裁剪到 60 且 hasMore=false
    vi.mocked(communityApi.fetchFeed).mockResolvedValueOnce(
      page(Array.from({ length: 60 }, (_, i) => post(i + 11)), 'c2', true),
    )
    await store.loadMore()
    expect(store.items).toHaveLength(60)
    expect(store.hasMore).toBe(false)
  })
})
