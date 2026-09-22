/**
 * 实时分 → 等级（2026-09-22 深色录唱页顶部评级条）。
 *
 * 参考图顶部是「A 2.63」这类实时评级；我们**不新造指标**——等级由现有实时分
 * （`lib/live-score.ts` 的近 5 秒在调率 × 出声率，练习参考口径）映射得到，
 * 分数段与 `live-chart.scoreColorOf` 的分档一致（85 / 60 两个既有阈值），
 * 便于「同分同色」跨组件自洽。
 *
 * 纯函数、零依赖；`null`（参考不足/未出声）→ `null`（界面显示占位，不猜等级）。
 */

export type GradeLetter = 'S' | 'A' | 'B' | 'C' | 'D'

export interface Grade {
  letter: GradeLetter
  /** 该等级的代表色（深色底上的文字/描边色） */
  color: string
}

/** 分档（由高到低；`min` = 该档下限，含） */
export const GRADE_BANDS: { letter: GradeLetter; min: number; color: string }[] = [
  { letter: 'S', min: 95, color: '#ffc83d' },
  { letter: 'A', min: 85, color: '#18a058' },
  { letter: 'B', min: 70, color: '#5ad2c0' },
  { letter: 'C', min: 60, color: '#f2a43a' },
  { letter: 'D', min: 0, color: '#d03050' },
]

/** 实时分 → 等级（null/NaN → null；越界夹取） */
export function gradeOf(score: number | null | undefined): Grade | null {
  if (score == null || !Number.isFinite(score)) return null
  const s = Math.min(100, Math.max(0, score))
  const band = GRADE_BANDS.find((b) => s >= b.min) ?? GRADE_BANDS[GRADE_BANDS.length - 1]
  return { letter: band.letter, color: band.color }
}

/** 顶部条进度（0~1；null → 0）：只表示实时分本身，不是歌曲进度 */
export function gradeProgress(score: number | null | undefined): number {
  if (score == null || !Number.isFinite(score)) return 0
  return Math.min(100, Math.max(0, score)) / 100
}
