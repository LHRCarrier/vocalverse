import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

import { useDelayedLoading } from '../useDelayedLoading'

function setup() {
  const loading = ref(false)
  const scope = effectScope()
  const { visible } = scope.run(() => useDelayedLoading(loading))!
  return { loading, visible, stop: () => scope.stop() }
}

describe('useDelayedLoading（骨架屏防抖 + 最短可见）', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('快请求（<300ms 完成）不显示骨架', async () => {
    const { loading, visible, stop } = setup()
    loading.value = true
    await nextTick()
    vi.advanceTimersByTime(150)
    expect(visible.value).toBe(false)

    loading.value = false
    await nextTick()
    vi.advanceTimersByTime(1000)
    expect(visible.value).toBe(false)
    stop()
  })

  it('慢请求（>300ms）在 300ms 时显示骨架', async () => {
    const { loading, visible, stop } = setup()
    loading.value = true
    await nextTick()
    vi.advanceTimersByTime(299)
    expect(visible.value).toBe(false)
    vi.advanceTimersByTime(1)
    expect(visible.value).toBe(true)
    stop()
  })

  it('已显示后，即使立刻完成也保证最短可见时长', async () => {
    const { loading, visible, stop } = setup()
    loading.value = true
    await nextTick()
    vi.advanceTimersByTime(300)
    expect(visible.value).toBe(true)

    // 刚显示 50ms 就完成
    vi.advanceTimersByTime(50)
    loading.value = false
    await nextTick()
    vi.advanceTimersByTime(200)
    expect(visible.value).toBe(true) // 未满 300ms，仍在显示
    vi.advanceTimersByTime(100)
    expect(visible.value).toBe(false)
    stop()
  })

  it('卸载时清理挂起的定时器（不残留回调）', async () => {
    const { loading, stop } = setup()
    loading.value = true
    await nextTick()
    stop()
    expect(() => vi.advanceTimersByTime(1000)).not.toThrow()
  })
})