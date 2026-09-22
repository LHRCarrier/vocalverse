/**
 * 跟唱歌词对轴纯函数测试（lib/sing-lyrics，2026-09-21 卡拉OK式滚动）。
 * 覆盖：归一与 endMs 三级推断、当前句判定（含边界/空隙/越界）、句内进度、
 * 以及「参考播放 vs 跟唱录音」双时钟解析（滚动频率一致的关键）。
 */
import { describe, expect, it } from 'vitest'

import {
  activeLineIndex,
  dimLevel,
  formatClock,
  lineDistance,
  lineProgress,
  nearestLineIndex,
  noteSpans,
  resolveLyricTimeMs,
  spanProgress,
  toLyricLines,
} from '@/lib/sing-lyrics'

const raw = [
  { seq: 1, start_ms: 0, end_ms: 1000, text: 'a' },
  { seq: 2, start_ms: 1000, text: 'b' }, // 无 end_ms → 用下一句 start 推断
  { seq: 3, start_ms: 3000, end_ms: 4000, text: 'c' },
]

describe('sing-lyrics · toLyricLines', () => {
  it('按 start_ms 升序，保留 seq/text', () => {
    const l = toLyricLines([raw[2], raw[0], raw[1]])
    expect(l.map((x) => x.seq)).toEqual([1, 2, 3])
    expect(l.map((x) => x.text)).toEqual(['a', 'b', 'c'])
  })

  it('endMs 三级推断：显式 end_ms → 下一句 start_ms → startMs+2000（末句兜底）', () => {
    const l = toLyricLines(raw)
    expect(l[0].endMs).toBe(1000) // 显式
    expect(l[1].endMs).toBe(3000) // 下一句 start
    expect(l[2].endMs).toBe(4000) // 显式
    expect(toLyricLines([{ seq: 1, start_ms: 500, text: 'x' }])[0].endMs).toBe(2500) // 兜底
  })

  it('过滤坏条目（缺/非数值/负 start_ms）；空/undefined 输入 → 空数组', () => {
    const l = toLyricLines([
      { seq: 1, start_ms: 0, text: 'ok' },
      { seq: 2, text: 'no-start' },
      { seq: 3, start_ms: Number.NaN, text: 'nan' },
      { seq: 4, start_ms: -5, text: 'neg' },
      null,
    ])
    expect(l).toHaveLength(1)
    expect(l[0].text).toBe('ok')
    expect(toLyricLines(null)).toEqual([])
    expect(toLyricLines(undefined)).toEqual([])
  })

  it('倒序/等于 start 的显式 end_ms 不算数（走下一级），退化区间被兜底撑开', () => {
    const l = toLyricLines([
      { seq: 1, start_ms: 0, end_ms: 0, text: 'a' },
      { seq: 2, start_ms: 1000, text: 'b' },
    ])
    expect(l[0].endMs).toBe(1000) // end=0 非法 → 用下一句 start
    expect(l[1].endMs).toBe(3000) // 末句兜底
  })
})

describe('sing-lyrics · activeLineIndex', () => {
  const lines = toLyricLines(raw) // 0-1000 / 1000-3000 / 3000-4000

  it('早于首句 → -1', () => {
    expect(activeLineIndex(lines, -1)).toBe(-1)
  })

  it('边界：恰好等于 startMs 即命中该句', () => {
    expect(activeLineIndex(lines, 0)).toBe(0)
    expect(activeLineIndex(lines, 1000)).toBe(1)
    expect(activeLineIndex(lines, 3000)).toBe(2)
  })

  it('句间空隙保持上一句（K 歌语义，不回退）', () => {
    expect(activeLineIndex(lines, 999)).toBe(0)
    expect(activeLineIndex(lines, 2500)).toBe(1)
  })

  it('晚于末句仍为末句；空数组 → -1', () => {
    expect(activeLineIndex(lines, 99_999)).toBe(2)
    expect(activeLineIndex([], 500)).toBe(-1)
  })
})

describe('sing-lyrics · lineProgress', () => {
  const lines = toLyricLines(raw)

  it('句内线性映射 0 → 0.5 → 1', () => {
    expect(lineProgress(lines, 0, 0)).toBe(0)
    expect(lineProgress(lines, 0, 500)).toBe(0.5)
    expect(lineProgress(lines, 0, 1000)).toBe(1)
  })

  it('越界 clamp（句前 0 / 句后 1）', () => {
    expect(lineProgress(lines, 2, 0)).toBe(0)
    expect(lineProgress(lines, 2, 99_999)).toBe(1)
  })

  it('不存在的下标 / 退化区间 → 0', () => {
    expect(lineProgress(lines, 9, 100)).toBe(0)
    const degenerate = [{ seq: 1, startMs: 100, endMs: 100, text: 'x', midi: null }]
    expect(lineProgress(degenerate, 0, 100)).toBe(0)
  })
})

/**
 * 句内逐字节奏（2026-09-22 用户口径：整句对得上，但唱得有快有慢、唱到哪个字对不上）。
 * 数据源 = `pitch_ref.midi` 逐帧音高（hop 32ms）→ 音符段 → 按段均分字推进。
 */
describe('sing-lyrics · 句内逐字节奏（noteSpans / spanProgress）', () => {
  /** 用「帧游程」拼 MIDI 数组：[帧数, midi 值]；-1 = 无音高 */
  const midiOf = (runs: [number, number][]) => {
    const out: number[] = []
    for (const [frames, v] of runs) for (let i = 0; i < frames; i += 1) out.push(v)
    return out
  }

  it('noteSpans：同音成段、换音分段、无音高断开（长休止不跨）', () => {
    // 10 帧 60（320ms）→ 10 帧 62 → 5 帧静音（160ms）→ 15 帧 64
    const spans = noteSpans(midiOf([[10, 60], [10, 62], [5, -1], [15, 64]]))
    expect(spans).toEqual([
      { startMs: 0, endMs: 320 },
      { startMs: 320, endMs: 640 },
      { startMs: 800, endMs: 1280 },
    ])
  })

  it('noteSpans：抖动碎音（<96ms）并入前段；相邻不同音仍保留各自边界（音符节拍点）', () => {
    // 10 帧 60 → 1 帧 61（32ms 跳音）→ 10 帧 60 → 10 帧 64
    const spans = noteSpans(midiOf([[10, 60], [1, 61], [10, 60], [10, 64]]))
    expect(spans).toEqual([
      { startMs: 0, endMs: 352 }, // 32ms 跳音并入前段
      { startMs: 352, endMs: 672 }, // 相邻不同音：不合并（保住音符边界）
      { startMs: 672, endMs: 992 },
    ])
  })

  it('noteSpans：短间隙（<120ms，塞音/快速换气）不拆段；无/空 MIDI → 空数组', () => {
    const spans = noteSpans(midiOf([[10, 60], [2, -1], [10, 62]])) // 64ms 间隙
    expect(spans).toEqual([{ startMs: 0, endMs: 704 }])
    expect(noteSpans(null)).toEqual([])
    expect(noteSpans([])).toEqual([])
    expect(noteSpans([-1, -1, null])).toEqual([])
  })

  it('spanProgress：段内推进该段负责的字、休止保持、首音前不抢跑、段尾到 1', () => {
    const spans = noteSpans(midiOf([[10, 60], [10, 62], [5, -1], [15, 64]]))
    const chars = 6 // 3 段 × 2 字
    expect(spanProgress(spans, chars, -50)).toBe(0) // 行首休止
    expect(spanProgress(spans, chars, 0)).toBe(0)
    expect(spanProgress(spans, chars, 160)).toBeCloseTo(1 / 6) // 第 1 段过半 → 第 1 字填一半
    expect(spanProgress(spans, chars, 320)).toBeCloseTo(2 / 6) // 第 1 段完
    expect(spanProgress(spans, chars, 480)).toBeCloseTo(3 / 6)
    expect(spanProgress(spans, chars, 700)).toBeCloseTo(4 / 6) // 休止中：保持
    expect(spanProgress(spans, chars, 800)).toBeCloseTo(4 / 6) // 第 3 段起点
    expect(spanProgress(spans, chars, 1040)).toBeCloseTo(5 / 6)
    expect(spanProgress(spans, chars, 1280)).toBe(1)
    expect(spanProgress(spans, chars, 99_999)).toBe(1)
  })

  it('spanProgress：快慢由音符结构决定——长音符填得慢、短音符填得快（不再按整句匀速）', () => {
    const spans = noteSpans(midiOf([[47, 60], [15, 62]])) // 长音 1504ms + 短音 480ms
    expect(spans).toEqual([
      { startMs: 0, endMs: 1504 },
      { startMs: 1504, endMs: 1984 },
    ])
    // 4 个字：前 2 个归长音（1.5s 才填完），后 2 个归短音（0.5s 填完）
    expect(spanProgress(spans, 4, 752)).toBeCloseTo(0.25) // 长音过半 → 只填了 1 个字
    expect(spanProgress(spans, 4, 1504)).toBeCloseTo(0.5)
    expect(spanProgress(spans, 4, 1984)).toBe(1)
    // 对照：线性口径在 752ms 已推进到 752/1984 ≈ 0.379（这就是「对不上字」的旧行为）
    expect(752 / 1984).toBeCloseTo(0.379, 2)
  })

  it('spanProgress：无音符数据/空文本 → null（调用方回退线性口径）', () => {
    expect(spanProgress([], 6, 100)).toBeNull()
    expect(spanProgress(noteSpans(midiOf([[10, 60]])), 0, 100)).toBeNull()
  })

  it('toLyricLines 带上 pitch_ref.midi（逐字节奏的数据通路）', () => {
    const [l] = toLyricLines([
      { seq: 1, start_ms: 0, end_ms: 1000, text: 'ab', pitch_ref: { midi: [60, 60, -1] } },
    ])
    expect(l.midi).toEqual([60, 60, -1])
    expect(toLyricLines([{ seq: 1, start_ms: 0, text: 'x' }])[0].midi).toBeNull()
  })
})

describe('sing-lyrics · formatClock（播放位置数字，取代传统进度条）', () => {
  it('mm:ss 补零；null/非法/负值 → --:--', () => {
    expect(formatClock(0)).toBe('00:00')
    expect(formatClock(52_000)).toBe('00:52')
    expect(formatClock(65_000)).toBe('01:05')
    expect(formatClock(3_600_000)).toBe('60:00') // 超长不截断（分钟位自然增长）
    expect(formatClock(null)).toBe('--:--')
    expect(formatClock(Number.NaN)).toBe('--:--')
    expect(formatClock(-1)).toBe('--:--')
  })
})

describe('sing-lyrics · dimLevel（透明度渐隐级别，按用户视频模板）', () => {
  it('焦点句 0（最亮）；距离每远一句升一级，封顶 3；无焦点句 → 3（最淡）', () => {
    expect(dimLevel(0)).toBe(0)
    expect(dimLevel(1)).toBe(1)
    expect(dimLevel(2)).toBe(2)
    expect(dimLevel(3)).toBe(3)
    expect(dimLevel(9)).toBe(3) // 封顶
    expect(dimLevel(Number.POSITIVE_INFINITY)).toBe(3)
  })
})

describe('sing-lyrics · nearestLineIndex（手动翻动时「始终聚焦视口中心的句子」）', () => {
  // 视口 550、行高 100、padTop = (550−100)/2 = 225（留白让首/末句也能居中）
  const boxH = 550
  const L = 100
  const pad = 225

  it('某句居中时 → 返回该句（视口中心正落在它的中线上）', () => {
    // 第 i 句居中 ⟺ scrollTop = pad + i·L + L/2 − boxH/2；i=2 → 225 + 200 + 50 − 275 = 200
    expect(nearestLineIndex(200, boxH, pad, L, 10)).toBe(2)
  })

  it('滚动不足半行 → 仍取近的那句；超过半行 → 取下一句（四舍五入）', () => {
    // 切换点在 scrollTop = 250（(center−pad)/L 越过 3）
    expect(nearestLineIndex(240, boxH, pad, L, 10)).toBe(2)
    expect(nearestLineIndex(260, boxH, pad, L, 10)).toBe(3)
  })

  it('越界夹到 [0, count−1]；退化入参 → −1（不抛错）', () => {
    expect(nearestLineIndex(0, boxH, pad, L, 3)).toBe(0)
    expect(nearestLineIndex(99_999, boxH, pad, L, 3)).toBe(2)
    expect(nearestLineIndex(0, 0, 0, 0, 5)).toBe(-1)
    expect(nearestLineIndex(0, boxH, pad, L, 0)).toBe(-1)
  })
})

describe('sing-lyrics · lineDistance', () => {
  it('无当前句 → Infinity（不虚化任何句）；否则为绝对距离', () => {
    expect(lineDistance(-1, 0)).toBe(Number.POSITIVE_INFINITY)
    expect(lineDistance(3, 1)).toBe(2)
    expect(lineDistance(3, 3)).toBe(0)
  })
})

describe('sing-lyrics · resolveLyricTimeMs（双时钟：滚动频率一致的关键）', () => {
  const base = {
    playing: false,
    audioMs: 0,
    recording: false,
    recStartAt: null,
    voiceAtMs: null,
    firstLineMs: 0,
    now: 0,
  }

  it('参考播放中 → 取音频位置（严格对齐音频）', () => {
    expect(resolveLyricTimeMs({ ...base, playing: true, audioMs: 12_345 })).toBe(12_345)
  })

  it('跟唱：开口那一刻游标 = 首句起点（锚点语义）', () => {
    // 录音 3s 时才开口（voiceAtMs=3000），首句 startMs=8000
    const t = resolveLyricTimeMs({
      ...base,
      recording: true,
      recStartAt: 1000,
      voiceAtMs: 3000,
      firstLineMs: 8000,
      now: 4000, // 开口后 0ms
    })
    expect(t).toBe(8000)
  })

  it('跟唱：开口后按与参考相同速率推进（句间距不变 → 频率一致）', () => {
    const at = (elapsedAfterVoice: number) =>
      resolveLyricTimeMs({
        ...base,
        recording: true,
        recStartAt: 1000,
        voiceAtMs: 3000,
        firstLineMs: 8000,
        now: 1000 + 3000 + elapsedAfterVoice,
      })
    expect(at(0)).toBe(8000)
    expect(at(5000)).toBe(13_000) // 与参考时间轴上「首句 +5s」完全一致
    expect(at(5000)! - at(0)!).toBe(5000) // 速率 1:1
  })

  it('尚未开口（voiceAtMs=null）→ null（歌词不预跑，停在顶部等开口）', () => {
    expect(
      resolveLyricTimeMs({ ...base, recording: true, recStartAt: 1000, voiceAtMs: null, now: 99_999 }),
    ).toBeNull()
  })

  it('两者都不在 → null', () => {
    expect(resolveLyricTimeMs(base)).toBeNull()
    expect(resolveLyricTimeMs({ ...base, recording: true, recStartAt: null, voiceAtMs: 0 })).toBeNull()
  })

  it('播放与录音同时为真 → 以播放为准（防御性确定行为）', () => {
    expect(
      resolveLyricTimeMs({
        ...base,
        playing: true,
        audioMs: 800,
        recording: true,
        recStartAt: 0,
        voiceAtMs: 0,
        now: 99_999,
      }),
    ).toBe(800)
  })

  it('负值被夹到 0（音频 currentTime 抖动 / 时钟回拨）', () => {
    expect(resolveLyricTimeMs({ ...base, playing: true, audioMs: -5 })).toBe(0)
    // 开口时刻晚于 now（时钟回拨）→ 已开口时长夹到 0，游标停在首句
    expect(
      resolveLyricTimeMs({ ...base, recording: true, recStartAt: 5000, voiceAtMs: 0, firstLineMs: 300, now: 1000 }),
    ).toBe(300)
  })
})
