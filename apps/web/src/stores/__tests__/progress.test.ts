/**
 * 学习进度 store（docs/53 P5 ③）：XP/等级来自服务端 `/api/v1/stats/progress`，
 * 本地只缓存快照；接口失败保留缓存（不写死 320 演示值）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useProgressStore } from '@/stores/progress'

const mocks = vi.hoisted(() => ({ fetchProgress: vi.fn() }))

vi.mock('@/api/stats', () => ({ fetchProgressSummary: mocks.fetchProgress }))

describe('useProgressStore（服务端 XP · docs/53 P5）', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })
  afterEach(() => localStorage.clear())

  it('冷启动无缓存 = 0 XP Lv1；refresh 后用服务端值与等级表', async () => {
    mocks.fetchProgress.mockResolvedValue({ xp: 320, level: 3, title: '对话能手', base: 250, next: 500 })
    const store = useProgressStore()
    expect(store.xp).toBe(0)
    expect(store.lvLabel).toBe('LV1')
    await store.refresh()
    expect(store.xp).toBe(320)
    expect(store.lvLabel).toBe('LV3')
    expect(store.xpInLevel).toBe(70)
    expect(store.nextXp).toBe(500)
    expect(store.progressPct).toBe(28)
  })

  it('refresh 失败保留缓存快照（离线仍显示上次等级）', async () => {
    mocks.fetchProgress.mockResolvedValue({ xp: 500, level: 4, title: '表达达人', base: 500, next: 900 })
    const store = useProgressStore()
    await store.refresh()
    expect(store.lvLabel).toBe('LV4')
    expect(JSON.parse(localStorage.getItem('vv_progress') ?? '{}').xp).toBe(500)

    mocks.fetchProgress.mockRejectedValue(new Error('net down'))
    await store.refresh()
    expect(store.xp).toBe(500)
    expect(store.lvLabel).toBe('LV4')
  })

  it('缓存恢复：整组快照读取，xp 与等级一致', () => {
    localStorage.setItem(
      'vv_progress',
      JSON.stringify({ xp: 900, level: 5, title: '流利大师', base: 900, next: null }),
    )
    const store = useProgressStore()
    expect(store.lvLabel).toBe('LV5')
    expect(store.progressPct).toBe(100)
    expect(store.nextXp).toBeNull()
  })
})
