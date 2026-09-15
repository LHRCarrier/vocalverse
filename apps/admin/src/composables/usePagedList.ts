import { computed, ref, shallowRef } from 'vue'

import { ApiError } from '@/api'
import type { PageView } from '@/api'

/**
 * 分页列表（控制台所有列表页统一用它）。
 *
 * 口径（docs/50 §8.5）：offset 分页 + 总数——控制台是低频人工操作，
 * 需要"共 N 条"这个信息，keyset 给不了；唯一例外是 trace 详情（不分页）。
 */
export interface PageQuery {
  page: number
  page_size: number
  [key: string]: unknown
}

export function usePagedList<T, Q extends Record<string, unknown>>(
  fetcher: (query: Q & { page: number; page_size: number }) => Promise<PageView<T>>,
  initialFilters: Q,
  pageSize = 20,
) {
  /**
   * ⚠️ 全部用 `shallowRef`，**不要** `ref(...) as { value: T }` 这种"假 ref"写法。
   * 假 ref 的类型不是 `Ref`，Vue 的模板类型检查就**不做自动解包**，
   * 于是每个页面都得写 `items.value` 才能渲染——统一踩坑（视图作者实测反馈）。
   * `shallowRef` 是真 `Ref`：模板里 `items` 就是 `T[]`，`filters` 就是 `Q`。
   */
  const items = shallowRef<T[]>([])
  const total = ref(0)
  const page = ref(1)
  const filters = shallowRef<Q>({ ...initialFilters })
  const loading = ref(false)
  const error = ref<string | null>(null)
  const errorCode = ref<number | null>(null)
  /**
   * 错误附带的结构化 data（docs/api/envelope.md「错误 data 的结构化例外」）。
   * 必须透出：46002 的 `required`（缺哪个权限码）与 46011 的 `violations[]`
   * 是给**用户看**的，只报 message 会让人不知道该找谁开权限、该补哪个字段。
   */
  const errorData = shallowRef<unknown>(null)

  const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    errorCode.value = null
    errorData.value = null
    try {
      const res = await fetcher({ ...filters.value, page: page.value, page_size: pageSize })
      items.value = res.items
      total.value = res.total
    } catch (err) {
      const e = err as ApiError
      error.value = e.message ?? '加载失败'
      errorCode.value = typeof e.code === 'number' ? e.code : null
      errorData.value = e.data ?? null
      items.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  /** 改筛选条件必须回到第 1 页——否则会停在越界页显示空列表 */
  async function applyFilters(next: Partial<Q>): Promise<void> {
    filters.value = { ...filters.value, ...next }
    page.value = 1
    await load()
  }

  async function reset(): Promise<void> {
    filters.value = { ...initialFilters }
    page.value = 1
    await load()
  }

  async function goPage(next: number): Promise<void> {
    page.value = Math.min(Math.max(1, next), pageCount.value)
    await load()
  }

  return {
    items,
    total,
    page,
    pageSize,
    pageCount,
    filters,
    loading,
    error,
    errorCode,
    errorData,
    load,
    applyFilters,
    reset,
    goPage,
  }
}
