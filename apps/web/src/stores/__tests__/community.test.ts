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
/** 带作者快照的帖子（改资料场景用：author.id 与「我」的 userId 比较） */
const authored = (id: number, authorId: number, nickname: string, handle: string | null, avatarUrl: string | null) =>
  ({ id, author: { id: authorId, nickname, handle, tint: null, level: 'L3', avatarUrl } }) as unknown as CommunityPostView

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

  /**
   * 2026-09-09 组长手机实测：发完帖回社区看不到，电脑刷新后才出现。
   * 根因 = `load()` 命中 domain 缓存就不发请求，而发帖在另一个页面 → 回首页看到旧快照。
   */
  it('prepend：新发帖立即置顶，且切回该 domain 不被旧缓存覆盖', async () => {
    const store = useCommunityStore()
    vi.mocked(communityApi.fetchFeed).mockResolvedValue(page([post(1)], 'c1', false))
    await store.load(null)
    expect(store.items.map((i) => i.id)).toEqual([1])
    expect(vi.mocked(communityApi.fetchFeed)).toHaveBeenCalledTimes(1)

    // 发帖成功 → prepend（发帖页调用）
    store.prepend(post(99))
    expect(store.items.map((i) => i.id)).toEqual([99, 1])

    // 回首页：命中缓存也必须带上刚发的帖（修复前是 [1]）
    await store.load(null)
    expect(store.items.map((i) => i.id)).toEqual([99, 1])
    expect(vi.mocked(communityApi.fetchFeed)).toHaveBeenCalledTimes(1)
  })

  it('prepend：同 id 去重（重复提交不出现两张卡）', async () => {
    const store = useCommunityStore()
    vi.mocked(communityApi.fetchFeed).mockResolvedValue(page([post(1)], 'c1', false))
    await store.load(null)
    store.prepend(post(99))
    store.prepend(post(99))
    expect(store.items.map((i) => i.id)).toEqual([99, 1])
  })

  it('invalidate：清缓存后 load 重新走网络', async () => {
    const store = useCommunityStore()
    vi.mocked(communityApi.fetchFeed).mockResolvedValue(page([post(1)], 'c1', false))
    await store.load(null)
    store.invalidate()
    await store.load(null)
    expect(vi.mocked(communityApi.fetchFeed)).toHaveBeenCalledTimes(2)
  })

  /**
   * 2026-09-14 组长手机实测：在「我的资料」改了头像和名称 → 社区列表卡片仍是旧头像/旧昵称，
   * **点进详情才更新**（同一屏顶栏已是新头像）。根因同 `prepend`：`load()` 命中 domain 缓存
   * 就不发请求，改资料发生在另一个页面 → 回首页看到的是改资料前的作者快照。
   */
  it('改资料后：本人作者快照就地更新，命中缓存也不回退旧昵称/旧头像', async () => {
    const store = useCommunityStore()
    vi.mocked(communityApi.fetchFeed).mockResolvedValue(
      page(
        [
          authored(1, 7, '成年中级', 'demo_adult', null),
          authored(2, 9, 'Emma', 'emmaenglish', '/api/v1/media/emma'),
        ],
        'c1',
        false,
      ),
    )
    await store.load(null)
    expect(store.items[0].author.nickname).toBe('成年中级')

    // 资料页保存成功 → 同步服务端回包
    store.applyMyProfile({ userId: 7, nickname: '林浩然', handle: 'lin', avatarUrl: '/api/v1/media/new' })

    expect(store.items[0].author.nickname).toBe('林浩然')
    expect(store.items[0].author.handle).toBe('lin')
    expect(store.items[0].author.avatarUrl).toBe('/api/v1/media/new')
    // 别人的作者快照不受影响
    expect(store.items[1].author.nickname).toBe('Emma')
    expect(store.items[1].author.avatarUrl).toBe('/api/v1/media/emma')

    // 返回社区首页：命中缓存（不发请求）也必须是新资料（修复前是旧昵称）
    await store.load(null)
    expect(vi.mocked(communityApi.fetchFeed)).toHaveBeenCalledTimes(1)
    expect(store.items[0].author.nickname).toBe('林浩然')
    expect(store.items[0].author.avatarUrl).toBe('/api/v1/media/new')
  })

  it('改资料：其他 domain 的缓存条目同步（切 Tab 不弹回旧昵称）', async () => {
    const store = useCommunityStore()
    // 每次请求返回**新对象**（真实链路每次 JSON 解析都是新实例 → 各 domain 缓存不共享引用）
    vi.mocked(communityApi.fetchFeed).mockImplementation(async () =>
      page([authored(1, 7, '成年中级', 'demo_adult', null)], 'c1', false),
    )
    await store.load('news')
    await store.load(null) // 两个 domain 各自入缓存

    store.applyMyProfile({ userId: 7, nickname: '林浩然', handle: null, avatarUrl: null })
    expect(store.items[0].author.nickname).toBe('林浩然')

    // 切回已缓存的 news：命中缓存也不回退（修复前是旧昵称）
    await store.load('news')
    expect(vi.mocked(communityApi.fetchFeed)).toHaveBeenCalledTimes(2)
    expect(store.items[0].author.nickname).toBe('林浩然')
    expect(store.items[0].author.handle).toBeNull()
  })

  it('applyMyProfile：userId 缺失时不动任何作者快照（宁可不改，不可改错人）', async () => {
    const store = useCommunityStore()
    vi.mocked(communityApi.fetchFeed).mockResolvedValue(
      page([authored(1, 7, '成年中级', 'demo_adult', null)], 'c1', false),
    )
    await store.load(null)
    store.applyMyProfile(null)
    store.applyMyProfile({ userId: 0, nickname: '林浩然' })
    expect(store.items[0].author.nickname).toBe('成年中级')
  })
})
