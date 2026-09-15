/**
 * `mono.ts` 几何/编码原语的单测（契约：这些函数是"图是否说谎"的地基，必须有测试兜底）。
 *
 * 覆盖 five 条硬性质：
 * 1. `rnd` 确定性且在 `[0,1)` —— 演示数据刷新两次必须长一样；
 * 2. `scale` 的退化区间（`d0 === d1`）不产生 `NaN`/`Infinity` —— 否则整张图会静默消失；
 * 3. `areaRadius` 满足**面积 ∝ 数值**（半径走 `sqrt`）—— 这条错了图就在放大差异；
 * 4. `capsuleBarTop` 对 `h <= 0` 返回空串 —— 0 值不能画出一条假柱子；
 * 5. `sect` 对整圆与部分扇区都产出合法 path —— 环形图的地基。
 */
import { describe, expect, it } from 'vitest'

import { areaRadius, capsuleBarTop, pol, rnd, scale, sect } from '../mono'

const isFiniteNumber = (v: number): boolean => Number.isFinite(v)

describe('rnd', () => {
  it('同一输入永远给同一输出', () => {
    expect(rnd(3, 7)).toBe(rnd(3, 7))
    expect(rnd(0, 0)).toBe(rnd(0, 0))
    expect(rnd(12345, 678)).toBe(rnd(12345, 678))
  })

  it('不同输入给不同输出（够用来做抖动）', () => {
    expect(rnd(1, 2)).not.toBe(rnd(2, 1))
  })

  it('永远落在 [0, 1)', () => {
    for (let i = 0; i < 60; i += 1) {
      for (let k = 0; k < 7; k += 1) {
        const v = rnd(i * 13 + 1, k * 5 + 3)
        expect(v).toBeGreaterThanOrEqual(0)
        expect(v).toBeLessThan(1)
      }
    }
  })
})

describe('scale', () => {
  it('正常区间按比例映射', () => {
    expect(scale(5, 0, 10, 0, 100)).toBe(50)
    expect(scale(0, 0, 10, 20, 30)).toBe(20)
    expect(scale(10, 0, 10, 20, 30)).toBe(30)
  })

  it('退化区间（d0 === d1）返回中点，且不是 NaN / Infinity', () => {
    const mid = scale(7, 4, 4, 0, 100)
    expect(isFiniteNumber(mid)).toBe(true)
    expect(mid).toBe(50)
    expect(isFiniteNumber(scale(0, 0, 0, 0, 0))).toBe(true)
  })
})

describe('areaRadius', () => {
  it('value = 0 → 半径 0；value = max → 半径 rMax', () => {
    expect(areaRadius(0, 100, 10)).toBe(0)
    expect(areaRadius(100, 100, 10)).toBe(10)
  })

  it('半径走 sqrt：面积 ∝ 数值', () => {
    const r25 = areaRadius(25, 100, 10)
    const r100 = areaRadius(100, 100, 10)
    expect(r25).toBeCloseTo(5, 10)
    // 面积比 = 数值比（4 倍），而不是半径比被当成数值比
    expect((Math.PI * r100 ** 2) / (Math.PI * r25 ** 2)).toBeCloseTo(4, 10)
  })

  it('max <= 0 时给 0，不产生 NaN', () => {
    expect(areaRadius(10, 0, 10)).toBe(0)
    expect(areaRadius(10, -1, 10)).toBe(0)
  })

  it('负值不产生虚数半径', () => {
    const r = areaRadius(-5, 100, 10)
    expect(isFiniteNumber(r)).toBe(true)
    expect(r).toBe(0)
  })
})

describe('capsuleBarTop', () => {
  it('h <= 0 返回空串（0 值不画假柱子）', () => {
    expect(capsuleBarTop(10, 20, 6, 0)).toBe('')
    expect(capsuleBarTop(10, 20, 6, -3)).toBe('')
  })

  it('h > 0 给一条闭合路径，圆角不超过半宽', () => {
    const d = capsuleBarTop(10, 20, 6, 40)
    expect(d.startsWith('M10 ')).toBe(true)
    expect(d.endsWith('Z')).toBe(true)
    expect(d).not.toContain('NaN')
    // 顶部圆角半径 = min(w/2, h) = 3
    expect(d).toContain('Q10 20 13 20')
  })

  it('矮柱子时圆角退化为 h（不倒扣）', () => {
    const d = capsuleBarTop(0, 0, 20, 2)
    expect(d).toContain('Q0 0 2 0')
  })
})

describe('sect', () => {
  it('整圆扫掠产出合法 path', () => {
    const d = sect(100, 100, 40, 60, 0, 360)
    expect(d).toMatch(/^M-?\d/)
    expect(d).toContain('A')
    expect(d).toContain('Z')
    expect(d).not.toContain('NaN')
    expect(d).not.toContain('Infinity')
  })

  it('部分扇区产出合法 path，且大弧标记按 >180° 切换', () => {
    const small = sect(50, 50, 10, 20, -90, 0)
    const big = sect(50, 50, 10, 20, -90, 180 + 1)
    expect(small).toMatch(/^M-?\d/)
    expect(small).toMatch(/A20\.00 20\.00 0 0 1/)
    expect(big).toMatch(/A20\.00 20\.00 0 1 1/)
    expect(small).not.toContain('NaN')
  })
})

describe('pol', () => {
  it('角度制极坐标换算（0° 在正右、90° 在正下）', () => {
    const [x0, y0] = pol(0, 0, 10, 0)
    expect(x0).toBeCloseTo(10, 10)
    expect(y0).toBeCloseTo(0, 10)
    const [x90, y90] = pol(0, 0, 10, 90)
    expect(x90).toBeCloseTo(0, 10)
    expect(y90).toBeCloseTo(10, 10)
  })
})
