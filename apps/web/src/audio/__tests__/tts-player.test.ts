/**
 * 听书播放状态机纯函数（docs/45 §5/§6：倍速四档 / 进度标签 / 预取窗口）。
 */
import { describe, expect, it } from 'vitest'

import { nextRate, prefetchWindow, progressLabel, RATES } from '../tts-player'

describe('RATES/nextRate', () => {
  it('四档循环', () => {
    expect(RATES).toHaveLength(4)
    expect(nextRate(1)).toBe(1.25)
    expect(nextRate(0.75)).toBe(1)
    expect(nextRate(1.5)).toBe(0.75)
  })
})

describe('progressLabel', () => {
  it('各状态标签', () => {
    expect(progressLabel({ state: 'idle', currentIdx: -1, total: 10, rate: 1 })).toBe('听书')
    expect(progressLabel({ state: 'playing', currentIdx: 2, total: 10, rate: 1 })).toBe('播放 3/10')
    expect(progressLabel({ state: 'paused', currentIdx: 2, total: 10, rate: 1 })).toBe('暂停 3/10')
    expect(progressLabel({ state: 'ended', currentIdx: 9, total: 10, rate: 1 })).toBe('已播完')
  })
})

describe('prefetchWindow', () => {
  it('预取 3 句、不越界、窗口为空返回空', () => {
    expect(prefetchWindow(0, 10, 3)).toEqual([1, 2, 3])
    expect(prefetchWindow(8, 10, 3)).toEqual([9])
    expect(prefetchWindow(9, 10, 3)).toEqual([])
  })
})
