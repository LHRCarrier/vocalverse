/**
 * 帖子评论数据流（社区 S3 · docs/47 §5.1）
 *
 * 详情页内联评论列表与 `MobileCommentsSheet` 的取数逻辑完全一致（keyset 游标、发表后顶部插入、
 * 计数同步），抽成 composable 让两处共用，避免「弹层与详情页两套评论逻辑」漂移。
 */
import { ref } from 'vue'

import { addComment, fetchComments } from '@/api/community'
import { useUiStore } from '@/stores/ui'

import type { CommentView } from '@/types/community'

export function usePostComments(postId: number, initialCount: number | (() => number) = 0) {
  const ui = useUiStore()
  const baseCount = typeof initialCount === 'function' ? initialCount : () => initialCount
  const list = ref<CommentView[]>([])
  const cursor = ref<string | null>(null)
  const hasMore = ref(false)
  const loading = ref(false)
  const loadingMore = ref(false)
  const added = ref(0)
  const draft = ref('')
  const submitting = ref(false)

  /** 展示计数 = 服务端总数 + 本次会话新增（父级按此同步卡片计数） */
  const total = () => baseCount() + added.value

  async function load(): Promise<void> {
    loading.value = true
    try {
      const page = await fetchComments(postId, null)
      list.value = page.items
      cursor.value = page.nextCursor
      hasMore.value = page.hasMore
    } catch (e) {
      ui.showToast(e instanceof Error ? e.message : '评论加载失败')
    } finally {
      loading.value = false
    }
  }

  async function loadMore(): Promise<void> {
    if (loadingMore.value || !hasMore.value || !cursor.value) return
    loadingMore.value = true
    try {
      const page = await fetchComments(postId, cursor.value)
      list.value = list.value.concat(page.items)
      cursor.value = page.nextCursor
      hasMore.value = page.hasMore
    } finally {
      loadingMore.value = false
    }
  }

  async function submit(): Promise<void> {
    const text = draft.value.trim()
    if (!text || submitting.value) return
    submitting.value = true
    try {
      const comment = await addComment(postId, text)
      list.value = [comment, ...list.value]
      added.value += 1
      draft.value = ''
    } catch (e) {
      ui.showToast(e instanceof Error ? e.message : '发表失败')
    } finally {
      submitting.value = false
    }
  }

  return { list, cursor, hasMore, loading, loadingMore, draft, submitting, total, load, loadMore, submit }
}
