/**
 * 唱歌评分纯函数（docs/06 §9.4 / docs/13 §5）：综合分 = 0.5·音准 + 0.2·节奏 + 0.3·发音。
 * 抽成纯函数便于 happy-dom 单测，不依赖任何 Vue / DOM。
 */
import type { SingLineScore } from '@/api/m3-types'

export const SING_WEIGHTS = { pitch: 0.5, rhythm: 0.2, pronunciation: 0.3 } as const

function clamp(v: number): number {
  return Math.min(100, Math.max(0, v))
}

/** 综合分：各句三维加权后取平均，四舍五入到 1 位小数。 */
export function computeComposite(lines: readonly SingLineScore[]): number {
  if (lines.length === 0) return 0
  const sum = lines.reduce(
    (acc, l) =>
      acc +
      SING_WEIGHTS.pitch * l.pitch +
      SING_WEIGHTS.rhythm * l.rhythm +
      SING_WEIGHTS.pronunciation * l.pronunciation,
    0,
  )
  return Math.round(clamp(sum / lines.length) * 10) / 10
}

/** 单句三维加权分（与综合分同一权重口径）。 */
export function computeLineTotal(line: SingLineScore): number {
  const v =
    SING_WEIGHTS.pitch * line.pitch +
    SING_WEIGHTS.rhythm * line.rhythm +
    SING_WEIGHTS.pronunciation * line.pronunciation
  return Math.round(clamp(v) * 10) / 10
}

/**
 * 确定性 0-100 假评分（mock 用）：同一种子稳定输出，避免每次刷新数值乱跳。
 * 正弦散列映射到 [55, 100) 区间，模拟"及格到优秀"的演示观感。
 */
export function deterministicScore(seed: number): number {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453
  const frac = x - Math.floor(x)
  return Math.round(clamp(55 + frac * 45))
}