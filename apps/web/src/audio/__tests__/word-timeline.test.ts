import { describe, expect, it } from 'vitest'

import {
  normalizeTimeline,
  startedWordIndex,
  timelineProgress,
  type WordSpan,
} from '../word-timeline'

const WORDS: Array<WordSpan | Record<string, unknown>> = [
  { word: "I'd", start: 0.12, end: 0.36 },
  { word: 'like', start: 0.38, end: 0.61 },
  { word: 'a', start: 0.64, end: 0.73 },
  { word: 'coffee', start: 0.75, end: 1.12 },
]

describe('word-timeline（B4 词级时间轴纯函数）', () => {
  it('normalizeTimeline：过滤坏条目并按 start 升序（容忍口径同后端 fluency.py）', () => {
    const out = normalizeTimeline([
      { word: 'beta', start: 0.5, end: 0.9 },
      { word: '', start: 0.1, end: 0.2 }, // 空词 → 丢弃
      { word: 'alpha', start: 0.1, end: 0.4 },
      { word: 'bad', start: 0.2, end: 0.2 }, // 零跨度 → 丢弃
      { word: 'nan', start: NaN, end: 0.5 }, // 非数值 → 丢弃
      null, // 直接 null 条目 → 丢弃
      undefined,
      { word: 'late', start: 1.0, end: 1.3 },
    ])
    expect(out).toEqual([
      { word: 'alpha', start: 0.1, end: 0.4 },
      { word: 'beta', start: 0.5, end: 0.9 },
      { word: 'late', start: 1.0, end: 1.3 },
    ])
    expect(normalizeTimeline([])).toEqual([])
    expect(normalizeTimeline(null)).toEqual([])
  })

  it('startedWordIndex：t<首词 → -1；词内/间隙 → 最新已开始；t≥末词 → 末词下标', () => {
    const tl = normalizeTimeline(WORDS)
    expect(startedWordIndex(tl, 0.0)).toBe(-1) // 首词前（录音导头静默）
    expect(startedWordIndex(tl, 0.12)).toBe(0) // 首词 start 边界
    expect(startedWordIndex(tl, 0.5)).toBe(1) // 词 1 内
    expect(startedWordIndex(tl, 0.62)).toBe(1) // 间隙（0.61~0.64）：保持上一词高亮（K 歌语义）
    expect(startedWordIndex(tl, 1.0)).toBe(3) // 末词内
    expect(startedWordIndex(tl, 5.0)).toBe(3) // 播放结束：停在末词
    expect(startedWordIndex([], 1.0)).toBe(-1) // 空时间轴
  })

  it('timelineProgress：首词 start → 0、末词 end → 1、越界 clamp、退化轴 → 0', () => {
    const tl = normalizeTimeline(WORDS)
    expect(timelineProgress(tl, 0.12)).toBe(0)
    expect(timelineProgress(tl, 1.12)).toBe(1)
    expect(timelineProgress(tl, 0.5)).toBeCloseTo((0.5 - 0.12) / (1.12 - 0.12), 5)
    expect(timelineProgress(tl, -1)).toBe(0)
    expect(timelineProgress(tl, 99)).toBe(1)
    expect(timelineProgress([], 0.5)).toBe(0)
    expect(timelineProgress([{ word: 'one', start: 0.5, end: 0.5 }], 0.5)).toBe(0) // 退化（end<=start 被过滤后为空）
  })
})
