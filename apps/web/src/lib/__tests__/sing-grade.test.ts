/**
 * 实时分 → 等级映射测试（lib/sing-grade，2026-09-22 深色录唱页顶部评级条）。
 *
 * 口径：等级只是**现有实时分**的表现层（不新造指标）；分数段与 `live-chart.scoreColorOf`
 * 的 85 / 60 阈值同源，保证「同分同色」；null/NaN → null（界面显示占位，不猜等级）。
 */
import { describe, expect, it } from 'vitest'

import { gradeOf, gradeProgress, GRADE_BANDS } from '@/lib/sing-grade'

describe('gradeOf', () => {
  it('按分数段给出等级与颜色', () => {
    expect(gradeOf(100)?.letter).toBe('S')
    expect(gradeOf(95)?.letter).toBe('S') // 边界含下限
    expect(gradeOf(94)?.letter).toBe('A')
    expect(gradeOf(85)?.letter).toBe('A') // 与 scoreColorOf 的 85 阈值同源
    expect(gradeOf(84)?.letter).toBe('B')
    expect(gradeOf(70)?.letter).toBe('B')
    expect(gradeOf(69)?.letter).toBe('C')
    expect(gradeOf(60)?.letter).toBe('C') // 与 scoreColorOf 的 60 阈值同源
    expect(gradeOf(59)?.letter).toBe('D')
    expect(gradeOf(0)?.letter).toBe('D')
  })

  it('null / NaN / 越界 → 占位或夹取（不抛异常）', () => {
    expect(gradeOf(null)).toBeNull()
    expect(gradeOf(undefined)).toBeNull()
    expect(gradeOf(Number.NaN)).toBeNull()
    expect(gradeOf(-10)?.letter).toBe('D')
    expect(gradeOf(120)?.letter).toBe('S')
  })

  it('颜色与分数段一致（同段同色、跨段不同色）', () => {
    expect(gradeOf(85)?.color).toBe(gradeOf(94)?.color) // 同一档 A
    expect(gradeOf(60)?.color).toBe(gradeOf(69)?.color) // 同一档 C
    expect(gradeOf(90)?.color).not.toBe(gradeOf(99)?.color) // A ≠ S
    const colors = GRADE_BANDS.map((b) => b.color)
    expect(new Set(colors).size).toBe(colors.length) // 各档颜色不重复
  })
})

describe('gradeProgress', () => {
  it('0~1 线性；null → 0；越界夹取', () => {
    expect(gradeProgress(0)).toBe(0)
    expect(gradeProgress(50)).toBe(0.5)
    expect(gradeProgress(100)).toBe(1)
    expect(gradeProgress(null)).toBe(0)
    expect(gradeProgress(150)).toBe(1)
    expect(gradeProgress(-5)).toBe(0)
  })
})
