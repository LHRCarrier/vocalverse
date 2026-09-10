/**
 * 社区 feed store（docs/37 §8 · docs/34 §5-1 状态结构：游标分页 + 刷新 + 乐观更新回滚）
 *
 * 数据源：Java /manage/api/v1/community/*（真实流）；领域 Tab 切换走服务端过滤
 * （domain 参数；null=为你推荐全量混排含打卡卡）。乐观更新约定：点赞/支持/评论先改本地，
 * 接口失败回滚 + toast；计数以后端返回为准（A-04/A-05）。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { coinPost, fetchFeed, likePost, sharePost } from '@/api/community'
import { useUiStore } from '@/stores/ui'

import type { CommunityPostView } from '@/types/community'

export const useCommunityStore = defineStore('community', () => {
  const items = ref<CommunityPostView[]>([])
  const cursor = ref<string | null>(null)
  const hasMore = ref(false)
  const loading = ref(false)
  const loadingMore = ref(false)
  const error = ref('')
  const activeDomain = ref<string | null>(null)

  const ui = useUiStore()

  /** fe-04：feed 列表上限（超出裁剪，防长列表 DOM/内存无界增长；虚拟化登记 P2） */
  const LIST_CAP = 60

  /** 请求序号守卫：仅最新一次 load/loadMore 可写回状态，旧响应（stale）一律丢弃（fe-03 竞态修复） */
  let loadSeq = 0
  let loadAbort: AbortController | null = null
  /** 按 domain 缓存上次结果：切回已加载领域免走网络+骨架屏；force=true（下拉刷新）才强制重拉 */
  const cache = new Map<string, { items: CommunityPostView[]; cursor: string | null; hasMore: boolean }>()

  const keyOf = (domain: string | null) => domain ?? ''

  /** 首屏/刷新/切领域：清空重拉（force 时忽略缓存） */
  async function load(domain: string | null, opts?: { force?: boolean }) {
    activeDomain.value = domain
    loadAbort?.abort()
    loadAbort = new AbortController()
    const mySeq = ++loadSeq
    const key = keyOf(domain)
    const cached = cache.get(key)
    if (cached && !opts?.force) {
      items.value = cached.items
      cursor.value = cached.cursor
      hasMore.value = cached.hasMore
      return
    }
    loading.value = true
    error.value = ''
    try {
      const page = await fetchFeed(domain, null, 10, loadAbort.signal)
      if (mySeq !== loadSeq) return
      items.value = page.items
      cursor.value = page.nextCursor
      hasMore.value = page.hasMore
      cache.set(key, { items: page.items, cursor: page.nextCursor, hasMore: page.hasMore })
    } catch (e) {
      if (mySeq !== loadSeq) return
      error.value = e instanceof Error ? e.message : '加载失败'
    } finally {
      if (mySeq === loadSeq) loading.value = false
    }
  }

  async function loadMore() {
    if (loadingMore.value || !hasMore.value || !cursor.value) return
    loadingMore.value = true
    const mySeq = ++loadSeq
    const domain = activeDomain.value
    const cur = cursor.value
    try {
      const page = await fetchFeed(domain, cur, 10, loadAbort?.signal)
      if (mySeq !== loadSeq) return
      const next = items.value.concat(page.items)
      // fe-04：上限裁剪防长列表 DOM/内存无界增长（虚拟化登记 P2）
      const capped = next.length > LIST_CAP ? next.slice(0, LIST_CAP) : next
      items.value = capped
      cursor.value = page.nextCursor
      hasMore.value = capped.length < next.length ? false : page.hasMore
      cache.set(keyOf(domain), { items: capped, cursor: page.nextCursor, hasMore: hasMore.value })
    } catch (e) {
      if (mySeq !== loadSeq) return
      ui.showToast(e instanceof Error ? e.message : '加载更多失败')
    } finally {
      if (mySeq === loadSeq) loadingMore.value = false
    }
  }

  function patchItem(id: number, patch: Partial<CommunityPostView>) {
    const target = items.value.find((p) => p.id === id)
    if (target) Object.assign(target, patch)
  }

  /**
   * 新发帖立即插到列表头（2026-09-09 组长实测：发完帖回社区看不到，刷新后才有）。
   *
   * 根因：`load()` 命中按 domain 缓存就**不发请求**，而发帖在另一个页面 —— 回首页时
   * 拿到的是发帖前的缓存快照。这里同时更新 items 与当前 domain 的缓存，回首页即见。
   */
  function prepend(post: CommunityPostView) {
    const next = [post, ...items.value.filter((p) => p.id !== post.id)]
    items.value = next.length > LIST_CAP ? next.slice(0, LIST_CAP) : next
    const key = keyOf(activeDomain.value)
    const cached = cache.get(key)
    cache.set(key, {
      items: items.value,
      cursor: cached?.cursor ?? cursor.value,
      hasMore: cached?.hasMore ?? hasMore.value,
    })
  }

  /** 失效全部缓存（下次 load 强制重拉） */
  function invalidate() {
    cache.clear()
  }

  /** 点赞 toggle（乐观 + 回滚；以后端返回计数为准） */
  async function toggleLike(post: CommunityPostView) {
    const target = items.value.find((p) => p.id === post.id) ?? post
    const next = !target.liked
    const prev = { liked: target.liked, likeCount: target.likeCount }
    target.liked = next
    target.likeCount = Math.max(0, target.likeCount + (next ? 1 : -1))
    try {
      const res = await likePost(post.id, next)
      patchItem(post.id, { liked: res.data.liked, likeCount: res.data.likeCount })
    } catch (e) {
      patchItem(post.id, prev)
      ui.showToast(e instanceof Error ? e.message : '操作失败')
    }
  }

  /** 支持（原投币）：不可取消、幂等——已支持再点仅提示 */
  async function coin(post: CommunityPostView) {
    const target = items.value.find((p) => p.id === post.id) ?? post
    if (target.coined) {
      ui.showToast('你已支持过这条内容（支持不可取消）')
      return
    }
    const prev = { coined: target.coined, coinCount: target.coinCount }
    target.coined = true
    target.coinCount = target.coinCount + 1
    try {
      const res = await coinPost(post.id)
      patchItem(post.id, { coined: res.data.coined, coinCount: res.data.coinCount })
    } catch (e) {
      patchItem(post.id, prev)
      ui.showToast(e instanceof Error ? e.message : '操作失败')
    }
  }

  /** 分享（一人一帖一次计数） */
  async function share(post: CommunityPostView) {
    try {
      const res = await sharePost(post.id)
      patchItem(post.id, { shareCount: res.data.shareCount })
    } catch (e) {
      ui.showToast(e instanceof Error ? e.message : '分享失败')
    }
  }

  /** 评论成功后同步计数（列表/追加由评论面板内部负责） */
  function syncCommentCount(id: number, count: number) {
    patchItem(id, { commentCount: count })
  }

  return {
    items,
    cursor,
    hasMore,
    loading,
    loadingMore,
    error,
    activeDomain,
    load,
    loadMore,
    toggleLike,
    coin,
    share,
    syncCommentCount,
    patchItem,
    prepend,
    invalidate,
  }
})
