/**
 * 跟唱「实时分」滚动统计（纯函数，可单测）。
 *
 * 口径（docs/06 §9.4 实时音准线注记补充，2026-09-18）：
 * - **练习参考，不参与离线评分、不进接口、不落库**；最终分以离线 pyin+DTW 为准（docs/08/25）。
 * - 滚动窗 5s，按检测 tick（~60ms）统计：
 *   refTicks    参考该时刻有声（f0>0）的 tick 数
 *   voicedTicks 参考有声且用户也检出音高的 tick 数
 *   tunedTicks  双方有声且 |cent 偏差| ≤ 50 的 tick 数
 * - `score = round(100 × tunedTicks / refTicks)`，即「在调率 × 出声率」的单比：
 *   对两件事同时单调（不唱 → 0；唱了跑调 → 0；只覆盖一半且全准 → 50），不需要额外加权。
 * - ±50 cent 对齐离线音准档（docs/06 §9.4「≤50 → 90+」），保证实时读数与报告口径可比。
 * - 护栏：refTicks < 5（≈0.3s）→ score = null（等待参考旋律 / 参考段全静音，UI 显示「—」）。
 *
 * 实现：3 个 Float64Array 环形；`read()` 整环重扫（容量 ≤ 127），不做增量回减——
 * 4Hz × 127 次迭代/秒的量级可忽略，但免掉"淘汰时回减算错"的整类 bug。
 */
import { REF_HOP_MS } from '@/lib/live-chart'

/** 滚动窗（ms） */
export const SCORE_WINDOW_MS = 5000
/** 「在调」判据（cent，对齐离线档） */
export const SCORE_TUNE_CENT = 50
/** 参考不足护栏（tick 数；≈0.3s） */
const MIN_REF_TICKS = 5
/** 环形容量按最小 tick 40ms 估（实际 tick 60ms → 容量富余，read 按时间戳过滤） */
const MIN_TICK_MS = 40

export interface LiveScoreRead {
  /** 0~100；参考不足 → null */
  score: number | null
  /** 唱到的音里在调的比例（0~1） */
  hitRate: number
  /** 参考有音处出声的比例（0~1） */
  sungRate: number
  refTicks: number
  voicedTicks: number
  tunedTicks: number
}

export interface LiveScore {
  /** 记一个 tick（refF0/userF0 为 0 表示该侧无声） */
  add: (tMs: number, refF0: number, userF0: number) => void
  /** 读当前滚动窗统计（`nowMs` = 该 tick 的时间戳，与 add 同一时间基） */
  read: (nowMs: number) => LiveScoreRead
  clear: () => void
}

/** 参考旋律按 32ms 槽查询（与绘制同源：live-chart.refF0At 的索引口径） */
export function refF0AtMs(ref: Float32Array | null, tMs: number): number {
  if (!ref?.length) return 0
  const i = Math.round(tMs / REF_HOP_MS)
  return i >= 0 && i < ref.length ? ref[i] : 0
}

export function createLiveScore(windowMs: number = SCORE_WINDOW_MS): LiveScore {
  const cap = Math.ceil(windowMs / MIN_TICK_MS) + 2
  const ts = new Float64Array(cap)
  const refs = new Float64Array(cap)
  const users = new Float64Array(cap)
  let head = 0
  let n = 0
  return {
    add(tMs, refF0, userF0) {
      const p = n < cap ? (head + n) % cap : head
      ts[p] = tMs
      refs[p] = refF0
      users[p] = userF0
      if (n < cap) n += 1
      else head = (head + 1) % cap
    },
    read(nowMs) {
      const from = nowMs - windowMs
      let refTicks = 0
      let voicedTicks = 0
      let tunedTicks = 0
      for (let i = 0; i < n; i += 1) {
        const p = (head + i) % cap
        if (ts[p] < from) continue
        const rf = refs[p]
        if (rf <= 0) continue
        refTicks += 1
        const uf = users[p]
        if (uf <= 0) continue
        voicedTicks += 1
        if (Math.abs(1200 * Math.log2(uf / rf)) <= SCORE_TUNE_CENT) tunedTicks += 1
      }
      return {
        score: refTicks >= MIN_REF_TICKS ? Math.round((100 * tunedTicks) / refTicks) : null,
        hitRate: voicedTicks ? tunedTicks / voicedTicks : 0,
        sungRate: refTicks ? voicedTicks / refTicks : 0,
        refTicks,
        voicedTicks,
        tunedTicks,
      }
    },
    clear() {
      head = 0
      n = 0
    },
  }
}