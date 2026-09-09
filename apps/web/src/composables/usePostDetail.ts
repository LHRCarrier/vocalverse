/**
 * 帖子详情数据流（社区 S3 · docs/47 §5.1）
 *
 * 为什么独立成 composable：详情页要承载「帖子 + 互动 + 评论 + 划词」，直接写在视图里必然破
 * `max-lines: 350`（eslint.config.js:32-35，docs/48 B22）。
 *
 * 与 feed store 的关系：详情页**自持状态**，互动成功后回写 store（`patchItem`）——
 * 但帖子可能不在当前 feed（从通知/搜索进入），此时回写是空操作，不影响详情页展示
 * （docs/48 §4 已登记）。
 */
import { ref } from 'vue'

import { coinPost, deletePost, fetchPost, likePost, sharePost } from '@/api/community'
import { useCommunityStore } from '@/stores/community'
import { useUiStore } from '@/stores/ui'

import type { CommunityPostView } from '@/types/community'

export function usePostDetail(postId: number) {
  const ui = useUiStore()
  const community = useCommunityStore()

  const post = ref<CommunityPostView | null>(null)
  const loading = ref(true)
  const error = ref('')
  const notFound = ref(false)
  const deleting = ref(false)

  async function load(): Promise<void> {
    loading.value = true
    error.value = ''
    notFound.value = false
    try {
      post.value = await fetchPost(postId)
    } catch (e) {
      // 40402 = 社区内容不存在或已删除（docs/api/error-codes.md）
      const code = (e as { code?: number }).code
      if (code === 40402 || code === 40401) notFound.value = true
      error.value = e instanceof Error ? e.message : '加载失败'
    } finally {
      loading.value = false
    }
  }

  function sync(patch: Partial<CommunityPostView>): void {
    if (post.value) Object.assign(post.value, patch)
    community.patchItem(postId, patch)
  }

  async function toggleLike(): Promise<void> {
    const p = post.value
    if (!p) return
    const next = !p.liked
    sync({ liked: next, likeCount: Math.max(0, p.likeCount + (next ? 1 : -1)) })
    try {
      const res = await likePost(p.id, next)
      sync({ liked: res.data.liked, likeCount: res.data.likeCount })
    } catch (e) {
      sync({ liked: p.liked, likeCount: p.likeCount })
      ui.showToast(e instanceof Error ? e.message : '操作失败')
    }
  }

  async function coin(): Promise<void> {
    const p = post.value
    if (!p) return
    if (p.coined) {
      ui.showToast('你已支持过这条内容（支持不可取消）')
      return
    }
    const prev = { coined: p.coined, coinCount: p.coinCount }
    sync({ coined: true, coinCount: p.coinCount + 1 })
    try {
      const res = await coinPost(p.id)
      sync({ coined: res.data.coined, coinCount: res.data.coinCount })
    } catch (e) {
      sync(prev)
      ui.showToast(e instanceof Error ? e.message : '操作失败')
    }
  }

  async function share(): Promise<void> {
    const p = post.value
    if (!p) return
    try {
      const res = await sharePost(p.id)
      sync({ shareCount: res.data.shareCount })
    } catch (e) {
      ui.showToast(e instanceof Error ? e.message : '分享失败')
    }
  }

  /** 删除自己的帖子（后端软删；成功后由视图决定去哪） */
  async function remove(): Promise<boolean> {
    const p = post.value
    if (!p || deleting.value) return false
    deleting.value = true
    try {
      await deletePost(p.id)
      community.items = community.items.filter((it) => it.id !== p.id)
      ui.showToast('已删除')
      return true
    } catch (e) {
      ui.showToast(e instanceof Error ? e.message : '删除失败')
      return false
    } finally {
      deleting.value = false
    }
  }

  return { post, loading, error, notFound, deleting, load, toggleLike, coin, share, remove }
}
