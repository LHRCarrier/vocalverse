/**
 * 听书播放器状态机（纯逻辑 · 零 DOM）：句队列加载 → 单元素顺序播放 → 句级高亮。
 *
 * 设计（docs/45 §6 · UI 拷问 U 系列）：
 * - 播放主线 = 「播放即取」：句 idx 单句端点 → Blob → objectURL 顺序播放；预取 N=3；
 * - 倍速用 <audio>.playbackRate（统一 0.75~1.5，四档；免多档重合成，docs/45 §5 拍板）；
 * - 状态：idle → loading(idx) → playing(idx) → paused(idx) → ended；失败跳句不卡队列；
 * - 与「点击查词/划词」互斥由视图层协调（长按划选 → pause()）。
 */
export type PlayerState = 'idle' | 'loading' | 'playing' | 'paused' | 'ended' | 'error'

export interface PlayerSnapshot {
  state: PlayerState
  currentIdx: number
  total: number
  rate: number
}

export const RATES = [0.75, 1, 1.25, 1.5] as const

export function nextRate(current: number): number {
  const i = RATES.findIndex((r) => Math.abs(r - current) < 1e-6)
  return RATES[(i + 1) % RATES.length]
}

/** 进度标签：当前句状态（x/y） → '播放 x/y' 等 */
export function progressLabel(s: PlayerSnapshot): string {
  if (s.state === 'idle') return '听书'
  if (s.state === 'ended') return '已播完'
  const base = `${Math.min(s.currentIdx + 1, s.total)}/${s.total}`
  if (s.state === 'loading') return `加载 ${base}`
  if (s.state === 'playing') return `播放 ${base}`
  if (s.state === 'paused') return `暂停 ${base}`
  return base
}

/** 播放完成一页/一句后的自动翻页提示：剩余句数（阈值内返回 true） */
export function shouldAdvance(s: PlayerSnapshot, autoAdvanceRemaining = 0): boolean {
  return s.state === 'ended' && s.currentIdx < s.total - 1 && autoAdvanceRemaining >= 0
}

/** 预取窗口：当前句后预取 N 句（0=关闭；返回待取句下标列表） */
export function prefetchWindow(currentIdx: number, total: number, n = 3): number[] {
  const out: number[] = []
  for (let i = 1; i <= n; i++) {
    const idx = currentIdx + i
    if (idx < total) out.push(idx)
  }
  return out
}
