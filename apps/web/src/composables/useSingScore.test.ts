import { describe, expect, it } from 'vitest'

import { computeComposite, computeLineTotal, deterministicScore } from './useSingScore'

describe('computeComposite', () => {
  it('按 0.5·音准 + 0.2·节奏 + 0.3·发音 取平均，保留 1 位小数', () => {
    const lines = [
      { lineIndex: 0, pitch: 80, rhythm: 90, pronunciation: 85 },
      { lineIndex: 1, pitch: 90, rhythm: 70, pronunciation: 80 },
    ]
    // 句0：40+18+25.5=83.5；句1：45+14+24=83；平均 83.25 → 83.3
    expect(computeComposite(lines)).toBe(83.3)
  })

  it('空数组返回 0', () => {
    expect(computeComposite([])).toBe(0)
  })
})

describe('computeLineTotal', () => {
  it('单句三维加权分', () => {
    expect(computeLineTotal({ lineIndex: 0, pitch: 80, rhythm: 90, pronunciation: 85 })).toBe(83.5)
  })
})

describe('deterministicScore', () => {
  it('同一种子稳定输出，且落在 [55, 100]', () => {
    const a = deterministicScore(7)
    const b = deterministicScore(7)
    expect(a).toBe(b)
    expect(a).toBeGreaterThanOrEqual(55)
    expect(a).toBeLessThanOrEqual(100)
  })
})