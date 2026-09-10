import { onBeforeUnmount, onMounted, shallowRef } from 'vue'
/**
 * 极简异步状态机（控制台所有异步区域统一用它，保证四态齐备）。
 *
 * 四态 = idle / loading / error / ready —— 少一个都会出现"白屏但没报错"，
 * 这是控制台最常见的体验缺陷（docs/50 §11.4）。
 */
export interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  errorCode: number | null
}

export function useAsync<T>(loader: () => Promise<T>) {
  /**
   * 用 `shallowRef` 而不是 `ref`：`ref<AsyncState<T>>` 会走 `UnwrapRef<T>` 的深解包，
   * 对泛型 `T` 往往推导成"部分解包"的类型，于是 **模板里拿到的不是解包值**，
   * 调用方被迫写 `state.value.value`（页面作者实测踩过）。
   * `shallowRef` 直接给 `AsyncState<T>`，模板自动解包成 `AsyncState<T>`，语义清晰。
   */
  const state = shallowRef<AsyncState<T>>({ data: null, loading: false, error: null, errorCode: null })
  const lastLoadedAt = shallowRef<number | null>(null)

  async function run(): Promise<T | null> {
    state.value.loading = true
    state.value.error = null
    state.value.errorCode = null
    try {
      const data = await loader()
      state.value.data = data
      lastLoadedAt.value = Date.now()
      return data
    } catch (err) {
      const e = err as { message?: string; code?: number }
      state.value.error = e.message ?? '加载失败'
      state.value.errorCode = typeof e.code === 'number' ? e.code : null
      return null
    } finally {
      state.value.loading = false
    }
  }

  return { state, run, lastLoadedAt }
}

/** 防抖：筛选条输入用（避免每敲一个字符打一次接口） */
export function debounce<A extends unknown[]>(fn: (...args: A) => void, wait = 300) {
  let timer: ReturnType<typeof setTimeout> | null = null
  return (...args: A): void => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn(...args), wait)
  }
}

/**
 * 会话轮询（控制台统一用它，别在页面里各自 setInterval）。
 *
 * 两个容易漏的点，这里一次解决：
 * 1. **组件卸载必须清定时器**——否则切页后定时器继续打接口（控制台用户会来回切页）；
 * 2. **标签页隐藏时暂停**——后台标签页每 15 秒打一次聚合查询，是纯粹浪费
 *    （控制台查询与学习者热路径共用同一个 PG，docs/50 §8.5）。
 */
export function useRealtimeRefresh(fn: () => void, intervalMs: number): void {
  let timer: ReturnType<typeof setInterval> | null = null

  const start = (): void => {
    if (timer) return
    timer = setInterval(fn, intervalMs)
  }
  const stop = (): void => {
    if (timer) clearInterval(timer)
    timer = null
  }
  const onVisibility = (): void => {
    if (document.hidden) {
      stop()
    } else {
      fn()
      start()
    }
  }

  onMounted(() => {
    start()
    document.addEventListener('visibilitychange', onVisibility)
  })
  onBeforeUnmount(() => {
    stop()
    document.removeEventListener('visibilitychange', onVisibility)
  })
}
