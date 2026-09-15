import { onBeforeUnmount, onMounted, shallowRef } from 'vue'
/**
 * 极简异步状态机（控制台所有异步区域统一用它，保证四态齐备）。
 *
 * 四态 = idle / loading / error / ready —— 少一个都会出现"白屏但没报错"，
 * 这是控制台最常见的体验缺陷（docs/50 §11.4）。
 *
 * ## ⚠️ 只能**整体替换** `state.value`，绝不要原地改它的属性（2026-09-10 实测缺陷）
 *
 * 状态用 `shallowRef` 存，而 `shallowRef` 的语义是：**只有 `.value` 被整体替换才触发更新**，
 * 改内层属性（`state.value.data = x`）**不触发任何依赖**（这正是它区别于 `ref` 的地方）。
 * 之前的写法就是原地改，后果**不是"偶尔不刷新"而是"恒不刷新"**：
 * 页面首帧 `data` 还是 null，接口 200 拿回数据写进 `state.value.data` 后，
 * 依赖它的 `computed` 永远不重算 —— **后端有数据、界面恒为空、且不报错**
 * （`error` 也是 null，四态里连"失败"都算不上）。实测：角色权限页后端返回 6 个角色，
 * 界面显示「角色数 0 / 还没有任何角色」；工作台/运维/指标/trace 等所有用本 composable
 * 的页面都是同一个症状。
 *
 * 所以统一走下面的 `patch()`（对象展开后整体赋值）。回归测试：
 * `composables/__tests__/useAsync.test.ts`（修复前 2/3 红）。
 *
 * 对照：`usePagedList` 用的是 `items.value = res.items`（整体替换）+ 各自独立的 `ref`，
 * 所以**列表页一直是好的** —— 这也正是当初没被发现的原因。
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

  /** 唯一的状态写入口：整体替换（原因见文件头注释） */
  function patch(next: Partial<AsyncState<T>>): void {
    state.value = { ...state.value, ...next }
  }

  async function run(): Promise<T | null> {
    patch({ loading: true, error: null, errorCode: null })
    try {
      const data = await loader()
      patch({ data, loading: false })
      lastLoadedAt.value = Date.now()
      return data
    } catch (err) {
      const e = err as { message?: string; code?: number }
      patch({
        error: e.message ?? '加载失败',
        errorCode: typeof e.code === 'number' ? e.code : null,
        loading: false,
      })
      return null
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
