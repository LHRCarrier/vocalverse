/**
 * 离散明度档 —— 热力/矩阵类图型共用的"明度即数据"换算。
 *
 * 为什么是**分位切档**而不是连续插值（契约硬约束，见 `chart-contract.md` F10）：
 * 24×7 或 8×12 的小格子上，连续渐变根本看不出档位；而按最大值等比例切档，
 * 一旦数据偏斜（真实工单/部署数据几乎总是偏斜）就会把九成格子压进最低一档，
 * 剩下的档位形同虚设。分位切档保证每一档都有格子落进去，读数才有梯度。
 *
 * 档位 → 颜色一律沿 `mono.LAD`（5 级灰阶）**反序**取：越黑 = 值越高。
 * Mono 无彩色，这里不引入任何色相。
 */
import { mono } from './mono'

/** 分位阈值（`count - 1` 个，升序）；没有正数样本时返回空数组 */
export function quantileBands(values: number[], count = mono.LAD.length): number[] {
  const pool = values.filter((v) => Number.isFinite(v) && v > 0).sort((a, b) => a - b)
  if (!pool.length || count < 2) return []
  const steps = Math.min(count, pool.length)
  return Array.from({ length: steps - 1 }, (_, k) =>
    pool[Math.floor(((k + 1) / steps) * (pool.length - 1))],
  )
}

/** 值 → 灰阶：超过第 k 个阈值就升一档，最后一档最黑 */
export function shadeOfBand(value: number, thresholds: number[]): string {
  const ladder = mono.LAD
  if (!thresholds.length) return ladder[ladder.length - 1]
  let band = 0
  for (const t of thresholds) if (value > t) band += 1
  return ladder[Math.max(0, ladder.length - 1 - band)]
}

/** 图例项：每档的色块 + 数值区间文字（低档在前，与格子从浅到深一致）
 *
 * 区间写成 `≤ x` / `> x` 的**不重叠**形式：分位阈值可能是小数（如 3.4），
 * 写成 "1–3 / 3–5" 这种闭区间在边界上会骗人（3 到底算哪一档？）。
 */
export function bandLegend(thresholds: number[], max: number): { color: string; text: string }[] {
  const ladder = mono.LAD
  const bands = thresholds.length + 1
  const fmt = (v: number): string => String(Math.round(v * 10) / 10)
  return Array.from({ length: bands }, (_, k) => {
    const high = k === bands - 1 ? max : thresholds[k]
    const text = k === 0 ? `≤ ${fmt(high)}` : `> ${fmt(thresholds[k - 1])}`
    return { color: ladder[Math.max(0, ladder.length - 1 - k)], text }
  })
}
