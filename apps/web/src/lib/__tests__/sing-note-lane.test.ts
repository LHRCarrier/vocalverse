/**
 * 音符引导条纯函数测试（lib/sing-note-lane，2026-09-22 深色录唱页新增）。
 *
 * 覆盖：① 逐句 midi → 整曲逐帧轨的对齐（按 `start_ms` 定位、未覆盖处 = NO_MIDI）；
 * ② 连续同值帧 → 音符块；NO_MIDI 断开；③ 过短碎块归并（避免画面上全是细缝）；
 * ④ 相邻同音块相接时再合并一次。
 */
import { describe, expect, it } from 'vitest'

import { flattenRefMidi, midiSegments, NO_MIDI } from '@/lib/sing-note-lane'
import { REF_HOP_MS } from '@/lib/live-chart'
import type { SongDetail } from '@/api/sing'

const detail = (over: Partial<SongDetail> = {}): SongDetail =>
  ({
    id: 1,
    title: 'T',
    level: 1,
    pitch_ref_status: 'ready',
    expected_lines: 2,
    favorited: false,
    duration_s: 10,
    lines: [
      {
        seq: 1,
        start_ms: 0,
        end_ms: 1000,
        text: 'a',
        pitch_ref: { midi: [60, 60, 62, 62], f0s: [261, 261, 293, 293] },
      },
      {
        seq: 2,
        start_ms: 2000,
        end_ms: 3000,
        text: 'b',
        pitch_ref: { midi: [64, 64], f0s: [329, 329] },
      },
    ],
    ...over,
  }) as SongDetail

describe('flattenRefMidi', () => {
  it('按句 start_ms 定位写入；句间空档 = NO_MIDI', () => {
    const track = flattenRefMidi(detail())
    const hop = REF_HOP_MS
    // 句 1：帧 0..3
    expect(Array.from(track.slice(0, 4))).toEqual([60, 60, 62, 62])
    // 句间空档（1000~2000ms）：帧 4 起先是空档再是句 2（2000ms / 32ms = 62.5 → 第 62 帧）
    const gapIdx = Math.floor(1000 / hop) + 1
    expect(track[gapIdx]).toBe(NO_MIDI)
    // 句 2 起点附近
    const s2 = Math.floor(2000 / hop)
    expect(Array.from(track.slice(s2, s2 + 2))).toEqual([64, 64])
  })

  it('缺 pitch_ref 的句不写脏数据（保持 NO_MIDI）', () => {
    const track = flattenRefMidi(
      detail({ lines: [{ seq: 1, start_ms: 0, end_ms: 500, text: 'x' }] as SongDetail['lines'] }),
    )
    expect(track.every((v) => v === NO_MIDI)).toBe(true)
  })
})

describe('midiSegments', () => {
  const hop = 32

  it('连续同值帧合成一段；NO_MIDI 断开', () => {
    // 60 × 4 帧（128ms ≥ 96）→ 一段；空档；64 × 4 帧 → 另一段
    const track = Float32Array.from([60, 60, 60, 60, NO_MIDI, NO_MIDI, 64, 64, 64, 64])
    const segs = midiSegments(track, hop)
    expect(segs).toEqual([
      { startMs: 0, endMs: 4 * hop, midi: 60 },
      { startMs: 6 * hop, endMs: 10 * hop, midi: 64 },
    ])
  })

  it('过短碎块并入前一块（画面不出现细缝）', () => {
    // 60 × 4 帧（128ms）+ 62 × 1 帧（32ms < 96）→ 合成一段（endMs 顺延，midi 保持前一块）
    const track = Float32Array.from([60, 60, 60, 60, 62])
    const segs = midiSegments(track, hop)
    expect(segs).toHaveLength(1)
    expect(segs[0].midi).toBe(60)
    expect(segs[0].endMs).toBe(5 * hop)
  })

  it('相邻同音块相接 → 再合并一次', () => {
    // 60×4（断开）60×4：中间空档仅 1 帧 → 归并后首尾相接 → 合成一段
    const track = Float32Array.from([60, 60, 60, 60, NO_MIDI, 60, 60, 60, 60])
    const segs = midiSegments(track, hop)
    expect(segs).toHaveLength(1)
    expect(segs[0]).toMatchObject({ startMs: 0, endMs: 9 * hop, midi: 60 })
  })

  it('空轨 → 空段（安全）', () => {
    expect(midiSegments(new Float32Array(0), hop)).toEqual([])
  })
})
