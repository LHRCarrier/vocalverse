import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useProgressStore } from '@/stores/progress'

describe('useProgressStore（Duolingo 式等级经验）', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })
  afterEach(() => localStorage.clear())

  it('默认 320 XP = LV3 对话能手，本级进度 28%', () => {
    const store = useProgressStore()
    expect(store.xp).toBe(320)
    expect(store.lvLabel).toBe('LV3')
    expect(store.info.title).toBe('对话能手')
    expect(store.xpInLevel).toBe(70) // 320 - 250
    expect(store.nextXp).toBe(500)
    expect(store.progressPct).toBe(28) // 70 / 250
  })

  it('addXp 升级：320 + 180 = 500 → LV4 表达达人，本级进度 0%；toast 弹出', () => {
    const store = useProgressStore()
    store.addXp(180)
    expect(store.xp).toBe(500)
    expect(store.lvLabel).toBe('LV4')
    expect(store.info.title).toBe('表达达人')
    expect(store.progressPct).toBe(0)
  })

  it('满级：≥900 → LV5 流利大师，进度 100%', () => {
    const store = useProgressStore()
    store.addXp(1000)
    expect(store.lvLabel).toBe('LV5')
    expect(store.progressPct).toBe(100)
    expect(store.nextXp).toBeNull()
  })
})
