/**
 * `useAsync` 的**响应式回归**（2026-09-10 实测缺陷）。
 *
 * ## 此前的问题
 *
 * `useAsync` 用 `shallowRef<AsyncState<T>>` 存状态，而 `run()` 是**原地改内层属性**
 * （`state.value.data = data`）。`shallowRef` 的语义是：**只有 `.value` 被整体替换才触发**，
 * 改内层属性**不触发任何更新**（这正是它区别于 `ref` 的地方）。
 *
 * 后果不是"偶尔不刷新"，而是**恒不刷新**：页面首次渲染时 `data` 还是 null，之后接口 200
 * 拿回数据、赋给 `state.value.data`，但依赖它的 `computed` 永远不重算
 * —— **后端有数据、界面恒为空、且不报错**（`error` 也是 null，四态里连"失败"都算不上）。
 * 实测表现：角色权限页后端返回 6 个角色，界面显示「角色数 0 / 还没有任何角色」。
 *
 * 对照组：`usePagedList` 写的是 `items.value = res.items`（整体替换）→ 列表页一直是好的。
 *
 * 本测试把"改内层必须能被观察到"钉死：修复前两条都失败，修复后必须绿。
 */
import { computed, nextTick } from 'vue'
import { describe, expect, it } from 'vitest'

import { useAsync } from '../useAsync'

describe('useAsync：状态变化必须能被 computed 观察到', () => {
  it('loader 成功后，依赖 state 的 computed 必须重算（修复前恒为初始值）', async () => {
    const { state, run } = useAsync(async () => [1, 2, 3])
    const len = computed(() => state.value.data?.length ?? 0)

    expect(len.value).toBe(0) // 首次渲染时的样子
    await run()
    await nextTick()

    expect(len.value).toBe(3)
    expect(state.value.loading).toBe(false)
    expect(state.value.error).toBeNull()
  })

  it('loading 的翻转也要可见（否则骨架屏永远不出现）', async () => {
    // `release!` 用明确赋值断言：赋值发生在 Promise executor 里，TS 的控制流分析看不到
    // （它无法知道 executor 是同步执行的），写成 `let release: (() => void) | null = null`
    // 会在调用点被收窄成 null 而编译失败。
    let release!: () => void
    const { state, run } = useAsync(
      () =>
        new Promise<number>((resolve) => {
          release = () => resolve(42)
        }),
    )
    const loading = computed(() => state.value.loading)

    expect(loading.value).toBe(false)
    const pending = run()
    await nextTick()
    expect(loading.value).toBe(true) // 修复前这里就已经是 false（不触发）

    release()
    await pending
    await nextTick()
    expect(loading.value).toBe(false)
    expect(state.value.data).toBe(42)
  })

  it('失败同样要落到 computed 上（错误码是排查线索，不能丢）', async () => {
    const { state, run } = useAsync(async () => {
      throw Object.assign(new Error('boom'), { code: 46002 })
    })
    const err = computed(() => state.value.error)
    const code = computed(() => state.value.errorCode)

    await run()
    await nextTick()

    expect(err.value).toBe('boom')
    expect(code.value).toBe(46002)
    expect(state.value.loading).toBe(false)
  })
})
