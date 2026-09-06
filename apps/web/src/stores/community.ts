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

  /** 首屏/刷新/切领域：清空重拉 */
  async function load(domain: string | null) {
    activeDomain.value = domain
    loading.value = true
    error.value = ''
    try {
      const page = await fetchFeed(domain, null)
      items.value = page.items
      cursor.value = page.nextCursor
      hasMore.value = page.hasMore
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载失败'
    } finally {
      loading.value = false
    }
  }

  async function loadMore() {
    if (loadingMore.value || !hasMore.value || !cursor.value) return
    loadingMore.value = true
    try {
      const page = await fetchFeed(activeDomain.value, cursor.value)
      items.value = items.value.concat(page.items)
      cursor.value = page.nextCursor
      hasMore.value = page.hasMore
    } catch (e) {
      ui.showToast(e instanceof Error ? e.message : '加载更多失败')
    } finally {
      loadingMore.value = false
    }
  }

  function patchItem(id: number, patch: Partial<CommunityPostView>) {
    const target = items.value.find((p) => p.id === id)
    if (target) Object.assign(target, patch)
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
  }
})
