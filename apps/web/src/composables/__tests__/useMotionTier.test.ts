import { describe, expect, it } from 'vitest'

import { detectMotionTier } from '../useMotionTier'

/** 构造 Window 替身（只覆盖探测用到的字段） */
function fakeWin(over: {
  reduce?: boolean
  cores?: number
  mem?: number
  saveData?: boolean
  search?: string
}): Window {
  return {
    location: { search: over.search ?? '' },
    matchMedia: () => ({ matches: over.reduce ?? false }),
    navigator: {
      hardwareConcurrency: over.cores,
      deviceMemory: over.mem,
      connection: { saveData: over.saveData },
    },
  } as unknown as Window
}

const store = (v: string | null): Storage => ({ getItem: () => v }) as unknown as Storage

describe('detectMotionTier（动效分级探测）', () => {
  it('默认（能力充足、无 reduced-motion）→ high', () => {
    expect(detectMotionTier(fakeWin({ cores: 8, mem: 8 }), store(null))).toBe('high')
  })

  it('系统"减少动效" → off', () => {
    expect(detectMotionTier(fakeWin({ reduce: true, cores: 8, mem: 8 }), store(null))).toBe('off')
  })

  it('低内存（deviceMemory ≤ 4）→ low', () => {
    expect(detectMotionTier(fakeWin({ mem: 4, cores: 8 }), store(null))).toBe('low')
  })

  it('低核数（≤ 4）→ low', () => {
    expect(detectMotionTier(fakeWin({ cores: 4, mem: 8 }), store(null))).toBe('low')
  })

  it('省数据模式 → low', () => {
    expect(detectMotionTier(fakeWin({ cores: 8, mem: 8, saveData: true }), store(null))).toBe('low')
  })

  it('iOS 无 deviceMemory → 不误降，保持 high', () => {
    expect(detectMotionTier(fakeWin({ cores: 6 }), store(null))).toBe('high')
  })

  it('localStorage 手动覆盖优先于能力探测', () => {
    expect(detectMotionTier(fakeWin({ mem: 2 }), store('high'))).toBe('high')
  })

  it('URL ?motion= 优先于 localStorage', () => {
    expect(detectMotionTier(fakeWin({ search: '?motion=off' }), store('low'))).toBe('off')
  })

  it('非法取值被忽略，回落到探测结果', () => {
    expect(detectMotionTier(fakeWin({ search: '?motion=abc', cores: 8, mem: 8 }), store('xyz'))).toBe('high')
  })
})