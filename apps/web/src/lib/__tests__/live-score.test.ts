/**
 * 跟唱「实时分」滚动统计测试（lib/live-score）——练习参考口径（docs/06 §9.4 注记）。
 * 覆盖：空窗护栏、全在调/全跑调、覆盖不足、窗口滚动淘汰、参考全静音、单比一致性。
 */
import { describe, expect, it } from 'vitest'

import { createLiveScore, refF0AtMs, SCORE_TUNE_CENT } from '@/lib/live-score'

const REF = 440
const TICK = 60

/** 正好越过阈值（50 + 1 cent）→ 判为跑调（守阈值语义） */
const JUST_OFF = REF * 2 ** ((SCORE_TUNE_CENT + 1) / 1200)

/** 在调（+45 cent，留出阈值浮点边界余量；阈值本身 = 50） */
const IN_TUNE = REF * 2 ** (45 / 1200)
/** 明显跑调（+120 cent） */
const OFF = REF * 2 ** (120 / 1200)

describe('live-score · createLiveScore', () => {
  it('空窗：无 tick → score null（护栏）', () => {
    const s = createLiveScore()
    const r = s.read(0)
    expect(r.score).toBeNull()
    expect(r.refTicks).toBe(0)
  })

  it('全在调 → 100；副读数 hitRate/sungRate 均为 1', () => {
    const s = createLiveScore()
    for (let i = 0; i < 10; i += 1) s.add(i * TICK, REF, IN_TUNE)
    const r = s.read(9 * TICK)
    expect(r.score).toBe(100)
    expect(r.hitRate).toBe(1)
    expect(r.sungRate).toBe(1)
  })

  it('全跑调 → 0（唱了但不在调）', () => {
    const s = createLiveScore()
    for (let i = 0; i < 10; i += 1) s.add(i * TICK, REF, OFF)
    const r = s.read(9 * TICK)
    expect(r.score).toBe(0)
    expect(r.hitRate).toBe(0)
    expect(r.sungRate).toBe(1)
  })

  it('只覆盖一半且全准 → 50（= 在调率 × 出声率 的单比）', () => {
    const s = createLiveScore()
    for (let i = 0; i < 10; i += 1) s.add(i * TICK, REF, i < 5 ? REF : 0)
    const r = s.read(9 * TICK)
    expect(r.score).toBe(50)
    expect(r.hitRate).toBe(1)
    expect(r.sungRate).toBe(0.5)
  })

  it('阈值语义：50 cent 内算在调（+45），越过 50（+51）算跑调', () => {
    const safe = createLiveScore()
    const over = createLiveScore()
    for (let i = 0; i < 10; i += 1) {
      safe.add(i * TICK, REF, IN_TUNE)
      over.add(i * TICK, REF, JUST_OFF)
    }
    expect(safe.read(9 * TICK).score).toBe(100)
    expect(over.read(9 * TICK).score).toBe(0)
  })

  it('参考有声 tick 不足 5 → null（等待参考旋律）', () => {
    const s = createLiveScore()
    for (let i = 0; i < 4; i += 1) s.add(i * TICK, REF, REF)
    expect(s.read(3 * TICK).score).toBeNull()
  })

  it('参考全静音 → null（该段无参考，不出分）', () => {
    const s = createLiveScore()
    for (let i = 0; i < 20; i += 1) s.add(i * TICK, 0, REF)
    expect(s.read(19 * TICK).score).toBeNull()
  })

  it('窗口滚动淘汰：5s 之前的 tick 不计入', () => {
    const s = createLiveScore()
    for (let i = 0; i < 10; i += 1) s.add(i * TICK, REF, REF) // t=0..540
    expect(s.read(540).score).toBe(100)
    // 6000ms 后：窗口 [1000, 6000]，旧 tick 全部出窗
    expect(s.read(6000).score).toBeNull()
  })

  it('score = round(100 × hitRate × sungRate)（单比一致性）', () => {
    const s = createLiveScore()
    for (let i = 0; i < 20; i += 1) {
      const refOn = i % 4 !== 3 // 参考 3/4 有声
      const userOn = i % 3 !== 2 // 用户 2/3 有声
      s.add(i * TICK, refOn ? REF : 0, userOn ? (i % 2 ? REF : OFF) : 0)
    }
    const r = s.read(19 * TICK)
    expect(r.score).toBe(Math.round(100 * r.hitRate * r.sungRate))
  })

  it('clear 后回到空窗', () => {
    const s = createLiveScore()
    s.add(0, REF, REF)
    s.clear()
    expect(s.read(0).refTicks).toBe(0)
  })
})

describe('live-score · refF0AtMs', () => {
  it('按 32ms 槽取参考；越界/空返回 0', () => {
    const ref = new Float32Array(4)
    ref[1] = 330
    expect(refF0AtMs(ref, 32)).toBe(330)
    expect(refF0AtMs(ref, 31)).toBe(330) // 四舍五入到最近槽
    expect(refF0AtMs(ref, 9999)).toBe(0)
    expect(refF0AtMs(null, 32)).toBe(0)
  })
})