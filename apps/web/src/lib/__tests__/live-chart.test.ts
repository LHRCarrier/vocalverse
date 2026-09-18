/**
 * 实时音准线绘制侧纯逻辑测试（lib/live-chart）：环形帧缓冲、参考旋律压平、窗口二分。
 * 背景：2026-09-18 性能改造（跟唱卡顿）——旧实现每帧重建数组 + 逐点走 Vue 代理，
 * 这里守住新结构的边界行为（容量/覆盖/清空/二分/句间空隙）。
 */
import { describe, expect, it } from 'vitest'

import type { SongDetail } from '@/api/sing'
import { createFrameRing, flattenRefF0s, REF_HOP_MS, renderChart } from '@/lib/live-chart'

function line(seq: number, startMs: number, f0s: number[]) {
  return {
    seq,
    start_ms: startMs,
    end_ms: startMs + f0s.length * REF_HOP_MS,
    text: `line ${seq}`,
    pitch_ref: { f0s },
  }
}

function detail(lines: ReturnType<typeof line>[]): SongDetail {
  return {
    id: 1,
    title: 'T',
    level: 1,
    pitch_ref_status: 'ready',
    expected_lines: lines.length,
    favorited: false,
    lines,
  }
}

describe('live-chart · createFrameRing', () => {
  it('未满：按插入顺序读出，length 正确', () => {
    const r = createFrameRing(4)
    r.push(0, 440)
    r.push(60, 441)
    expect(r.length()).toBe(2)
    expect(r.tAt(0)).toBe(0)
    expect(r.fAt(1)).toBe(441)
  })

  it('满员覆盖：保留最新 capacity 个（tMs 仍单调）', () => {
    const r = createFrameRing(2)
    r.push(0, 1)
    r.push(60, 2)
    r.push(120, 3)
    expect(r.length()).toBe(2)
    expect(r.tAt(0)).toBe(60)
    expect(r.tAt(1)).toBe(120)
    expect(r.fAt(0)).toBe(2)
  })

  it('wrap 多圈后仍有序，clear 归零', () => {
    const r = createFrameRing(3)
    for (let i = 0; i < 8; i += 1) r.push(i * 60, i)
    expect(r.length()).toBe(3)
    expect([r.tAt(0), r.tAt(1), r.tAt(2)]).toEqual([300, 360, 420])
    r.clear()
    expect(r.length()).toBe(0)
    expect(r.lowerBound(0)).toBe(0)
  })

  it('lowerBound：空环/早于全部/命中/晚于全部', () => {
    const r = createFrameRing(4)
    expect(r.lowerBound(100)).toBe(0)
    r.push(100, 1)
    r.push(200, 2)
    r.push(300, 3)
    expect(r.lowerBound(50)).toBe(0)
    expect(r.lowerBound(200)).toBe(1)
    expect(r.lowerBound(201)).toBe(2)
    expect(r.lowerBound(999)).toBe(3)
  })

  it('容量下限 1（防御）', () => {
    const r = createFrameRing(0)
    r.push(1, 440)
    r.push(2, 441)
    expect(r.length()).toBe(1)
    expect(r.tAt(0)).toBe(2)
  })
})

describe('live-chart · flattenRefF0s', () => {
  it('单句 start_ms=0：索引 = i（tMs/32）', () => {
    const ref = flattenRefF0s(detail([line(1, 0, [440, 0, 220])]))
    expect(ref.length).toBe(3)
    expect(ref[0]).toBe(440)
    expect(ref[1]).toBe(0)
    expect(ref[2]).toBe(220)
  })

  it('多句带间隔：句间为 0（断笔），句内按 start_ms 落位', () => {
    const ref = flattenRefF0s(detail([line(1, 0, [440, 440]), line(2, 320, [330, 330])]))
    expect(ref.length).toBe(10 + 2)
    expect(ref[0]).toBe(440)
    expect(ref[4]).toBe(0)
    expect(ref[10]).toBe(330)
  })

  it('start_ms 非 32 倍数：四舍五入到最近槽', () => {
    const ref = flattenRefF0s(detail([line(1, 50, [440])]))
    expect(ref.length).toBe(Math.round(50 / REF_HOP_MS) + 1)
    expect(ref[Math.round(50 / REF_HOP_MS)]).toBe(440)
  })

  it('缺 pitch_ref / 空句：长度为 0，不抛错', () => {
    expect(flattenRefF0s(detail([])).length).toBe(0)
    const noRef = detail([line(1, 0, [])])
    expect(flattenRefF0s(noRef).length).toBe(0)
  })
})

describe('live-chart · renderChart（假 ctx 冒烟：不抛错、不依赖 DOM）', () => {
  it('空环/空参考也能画（首帧即安全）', () => {
    const g = new Proxy({}, { get: () => () => {}, set: () => true }) as unknown as CanvasRenderingContext2D
    expect(() =>
      renderChart(g, { w: 340, h: 120, x1: 1000, playheadT: 500, headAlpha: 1, refF0s: new Float32Array(0), ring: createFrameRing(10) }),
    ).not.toThrow()
  })

  it('有数据 + 静音淡出路径也安全', () => {
    const g = new Proxy({}, { get: () => () => {}, set: () => true }) as unknown as CanvasRenderingContext2D
    const ring = createFrameRing(10)
    for (let i = 0; i < 10; i += 1) ring.push(900 + i * 60, 220 + i)
    expect(() =>
      renderChart(g, {
        w: 340,
        h: 120,
        x1: 1600,
        playheadT: 1500,
        headAlpha: 0.4,
        refF0s: flattenRefF0s(detail([line(1, 0, [440, 440, 440])])),
        ring,
      }),
    ).not.toThrow()
  })
})