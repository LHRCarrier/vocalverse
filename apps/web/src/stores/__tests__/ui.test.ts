import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useUiStore } from '@/stores/ui'

describe('useUiStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })
  afterEach(() => vi.useRealTimers())

  it('抽屉开关', () => {
    const store = useUiStore()
    expect(store.drawerOpen).toBe(false)
    store.openDrawer()
    expect(store.drawerOpen).toBe(true)
    store.closeDrawer()
    expect(store.drawerOpen).toBe(false)
  })

  it('toast：显示后自动消失（2.2s）', () => {
    const store = useUiStore()
    store.showToast('hi')
    expect(store.toastText).toBe('hi')
    vi.advanceTimersByTime(2300)
    expect(store.toastText).toBe('')
  })
})
