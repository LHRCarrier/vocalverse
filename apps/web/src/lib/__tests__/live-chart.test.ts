/**
 * 实时音准线绘制侧纯逻辑测试（lib/live-chart）：环形帧缓冲、参考旋律压平、窗口二分。
 * 背景：2026-09-18 性能改造（跟唱卡顿）——旧实现每帧重建数组 + 逐点走 Vue 代理，
 * 这里守住新结构的边界行为（容量/覆盖/清空/二分/句间空隙）。
 */
import { describe, expect, it } from 'vitest'

import type { SongDetail } from '@/api/sing'
import {
  createFrameRing,
  eachSilenceSpan,
  flattenRefF0s,
  octaveAlignedF0,
  REF_HOP_MS,
  renderChart,
  scoreColorOf,
} from '@/lib/live-chart'

/** 与 renderChart 内部一致的纵轴映射（h = 120） */
const y2f = (f: number) => 6 + (1 - (Math.log2(f) - Math.log2(65)) / (Math.log2(800) - Math.log2(65))) * (120 - 24)

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

describe('live-chart · eachSilenceSpan（没出声 → 底部灰线，2026-09-18 需求）', () => {
  const spans = (ring: ReturnType<typeof createFrameRing>, from: number, to: number, now: number) => {
    const out: Array<[number, number]> = []
    eachSilenceSpan(ring, from, to, now, (a, b) => out.push([a, b]))
    return out
  }

  it('尚无任何浊音帧：从录音开头画到当前（now>阈值）', () => {
    expect(spans(createFrameRing(8), 0, 1000, 1000)).toEqual([[0, 1000]])
  })

  it('短于阈值不画（刚开始 200ms 未出声 / 正常换气）', () => {
    expect(spans(createFrameRing(8), 0, 200, 200)).toEqual([])
  })

  it('首帧之前的空白段（起唱晚）', () => {
    const r = createFrameRing(8)
    r.push(500, 440)
    expect(spans(r, 0, 600, 600)).toEqual([[0, 500]])
  })

  it('帧间空隙 > 阈值 → 一段；< 阈值 → 不画', () => {
    const long = createFrameRing(8)
    long.push(0, 440)
    long.push(1500, 440)
    long.push(1560, 440)
    expect(spans(long, 0, 1560, 1560)).toEqual([[0, 1500]])
    const short = createFrameRing(8)
    short.push(0, 440)
    short.push(120, 440)
    expect(spans(short, 0, 120, 120)).toEqual([])
  })

  it('末帧之后仍在静音：延伸到 now（灰线实时增长）', () => {
    const r = createFrameRing(8)
    r.push(0, 440)
    r.push(60, 440)
    expect(spans(r, 0, 3000, 3000)).toEqual([[60, 3000]])
  })

  it('按可见窗与 t>=0 裁剪（窗口早于录音 / 晚于 now 均不越界）', () => {
    const r = createFrameRing(8)
    r.push(900, 440)
    expect(spans(r, 1000, 5000, 2000)).toEqual([[1000, 2000]]) // 左沿被 from 裁、右沿被 now 裁
    expect(spans(createFrameRing(8), -5000, 2000, 1000)).toEqual([[0, 1000]]) // t<0 不画
  })

  it('综合：起唱晚 + 中间长静音 + 末尾静音（三段）', () => {
    const r = createFrameRing(8)
    r.push(400, 440)
    r.push(460, 440)
    r.push(2000, 440)
    // 段落边界取「相邻浊音帧之间」（段起点 = 前一帧时刻，段终点 = 后一帧时刻）
    expect(spans(r, 0, 2600, 2600)).toEqual([
      [0, 400],
      [460, 2000],
      [2000, 2600],
    ])
  })
})

describe('live-chart · renderChart（假 ctx 冒烟：不抛错、不依赖 DOM）', () => {
  /** 记录每次「确有路径的」stroke 的颜色与末点 y（空路径的 stroke 在 canvas 上不画，不计） */
  function makeRecorder() {
    const strokes: Array<{ color: string; y: number }> = []
    const fills: Array<{ color: string; radius: number }> = []
    const calls: Record<string, number> = {}
    const state = { strokeStyle: '', fillStyle: '', lastY: 0, lastR: 0, pathOpen: false }
    const g = new Proxy(
      {},
      {
        get(_t, prop) {
          if (prop === 'strokeStyle') return state.strokeStyle
          if (prop === 'fillStyle') return state.fillStyle
          return (...args: unknown[]) => {
            const name = String(prop)
            calls[name] = (calls[name] ?? 0) + 1
            if (prop === 'beginPath') state.pathOpen = false
            if (prop === 'moveTo' || prop === 'lineTo' || prop === 'quadraticCurveTo') {
              state.pathOpen = true
              state.lastY = Number(args[args.length - 1])
            }
            if (prop === 'arc') state.lastR = Number(args[2])
            if (prop === 'stroke' && state.pathOpen) strokes.push({ color: state.strokeStyle, y: state.lastY })
            if (prop === 'fill') fills.push({ color: state.fillStyle, radius: state.lastR })
          }
        },
        set(_t, prop, value) {
          if (prop === 'strokeStyle') state.strokeStyle = String(value)
          if (prop === 'fillStyle') state.fillStyle = String(value)
          return true
        },
      },
    ) as unknown as CanvasRenderingContext2D
    return { g, strokes, fills, calls }
  }

  it('空环/空参考也能画（首帧即安全）', () => {
    const { g } = makeRecorder()
    expect(() =>
      renderChart(g, { w: 340, h: 120, x1: 1000, playheadT: 500, headAlpha: 1, refF0s: new Float32Array(0), ring: createFrameRing(10) }),
    ).not.toThrow()
  })

  it('有数据 + 静音淡出路径也安全', () => {
    const { g } = makeRecorder()
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

  it('静音段确实画成底部灰线（颜色 #b9bdbc、y = h - 9）', () => {
    const { g, strokes } = makeRecorder()
    const ring = createFrameRing(10)
    ring.push(1000, 440) // 0~1000ms 未出声
    renderChart(g, { w: 340, h: 120, x1: 2000, playheadT: 1100, headAlpha: 1, refF0s: new Float32Array(0), ring })
    const gray = strokes.filter((s) => s.color === '#b9bdbc')
    expect(gray.length).toBeGreaterThan(0)
    expect(gray.every((s) => s.y === 120 - 9)).toBe(true)
  })

  it('无静音段时不画灰线（连续出声）', () => {
    const { g, strokes } = makeRecorder()
    const ring = createFrameRing(32) // 容量须大于帧数，否则最旧帧被覆盖 → 首帧前被误判为静音
    for (let i = 0; i < 20; i += 1) ring.push(i * 60, 440)
    renderChart(g, { w: 340, h: 120, x1: 1200, playheadT: 1140, headAlpha: 1, refF0s: new Float32Array(0), ring })
    expect(strokes.filter((s) => s.color === '#b9bdbc')).toHaveLength(0)
  })

  it('八度等价：用户低一个八度也画在目标音符块上（2026-09-22「怎么唱都不在块内」）', () => {
    const { g, strokes } = makeRecorder()
    const ring = createFrameRing(16)
    for (let i = 0; i < 5; i += 1) ring.push(i * 60, 220) // 用户唱 A3（低一个八度）
    const refF0s = flattenRefF0s(detail([line(1, 0, Array.from({ length: 20 }, () => 440))])) // 参考 A4
    renderChart(g, { w: 340, h: 120, x1: 1000, playheadT: 300, headAlpha: 1, refF0s, ring })
    const trace = strokes.filter((s) => s.color === '#e07a3f')
    expect(trace.length).toBeGreaterThan(0)
    expect(trace[trace.length - 1].y).toBeCloseTo(y2f(440), 3) // 对齐到参考的八度，而不是 y2f(220)
  })

  it('参考缺失段沿用最近一次八度偏移（句间空隙不来回跳）', () => {
    const { g, strokes } = makeRecorder()
    const ring = createFrameRing(16)
    // 前 3 点有参考（440），后 3 点参考缺失（句间空隙）：仍应按 440 画
    const refF0s = flattenRefF0s(detail([line(1, 0, [440, 440, 440])]))
    for (let i = 0; i < 6; i += 1) ring.push(i * 60, 220)
    renderChart(g, { w: 340, h: 120, x1: 1000, playheadT: 400, headAlpha: 1, refF0s, ring })
    const trace = strokes.filter((s) => s.color === '#e07a3f')
    expect(trace[trace.length - 1].y).toBeCloseTo(y2f(440), 3)
  })

  it('octaveAlignedF0：纯函数边界（同八度不动 / ±1 八度回正 / 无参考不动）', () => {
    expect(octaveAlignedF0(440, 440)).toBe(440)
    expect(octaveAlignedF0(220, 440)).toBe(440)
    expect(octaveAlignedF0(880, 440)).toBe(440)
    expect(octaveAlignedF0(220, 0)).toBe(220) // 参考无声：保持原值
    expect(octaveAlignedF0(0, 440)).toBe(0)
    // 非整八度差（差 3 半音）不误判：仍取最近八度，但不会改变半音关系
    expect(octaveAlignedF0(440 * 2 ** (3 / 12), 440)).toBeCloseTo(440 * 2 ** (3 / 12), 6)
  })

  it('折线圆角化：多点轨迹用 quadraticCurveTo（不再逐段 lineTo）', () => {
    const { g, calls } = makeRecorder()
    const ring = createFrameRing(16)
    for (let i = 0; i < 5; i += 1) ring.push(i * 60, 220 + i * 10)
    renderChart(g, { w: 340, h: 120, x1: 1000, playheadT: 300, headAlpha: 1, refF0s: new Float32Array(0), ring })
    expect(calls.quadraticCurveTo ?? 0).toBeGreaterThan(0)
  })

  it('头部插值点替代原始末点（只影响最后一段：轨迹末端 y = 插值点对应的 y）', () => {
    const build = () => {
      const r = createFrameRing(16)
      r.push(0, 220)
      r.push(60, 220)
      r.push(120, 220)
      return r
    }
    const withHead = makeRecorder()
    renderChart(withHead.g, {
      w: 340,
      h: 120,
      x1: 1000,
      playheadT: 200,
      headAlpha: 1,
      refF0s: new Float32Array(0),
      ring: build(),
      head: { t: 180, f: 440 },
    })
    const raw = makeRecorder()
    renderChart(raw.g, {
      w: 340,
      h: 120,
      x1: 1000,
      playheadT: 200,
      headAlpha: 1,
      refF0s: new Float32Array(0),
      ring: build(),
    })
    const lastY = (s: Array<{ color: string; y: number }>) => s.filter((x) => x.color === '#e07a3f').at(-1)!.y
    expect(lastY(withHead.strokes)).toBeCloseTo(y2f(440), 0)
    expect(lastY(raw.strokes)).toBeCloseTo(y2f(220), 0)
    expect(Math.abs(lastY(withHead.strokes) - lastY(raw.strokes))).toBeGreaterThan(10)
  })

  it('静音段不画橙线：轨迹不随静音渐隐（各段同为实心），且静音后不残留橙点', () => {
    const ring = createFrameRing(16)
    for (let i = 0; i < 8; i += 1) ring.push(i * 60, 220 + i * 5)
    // headAlpha 随静音降到 0（组件侧 1 → 0，历时 FADE_MS）
    const silent = makeRecorder()
    renderChart(silent.g, { w: 340, h: 120, x1: 1000, playheadT: 600, headAlpha: 0, refF0s: new Float32Array(0), ring })
    // 轨迹本体仍画（历史保留），但**没有**橙点 fill
    expect(silent.strokes.some((s) => s.color === '#e07a3f')).toBe(true)
    expect(silent.fills.filter((f) => f.color === '#e07a3f')).toHaveLength(0)
    // 出声时橙点在
    const singing = makeRecorder()
    renderChart(singing.g, { w: 340, h: 120, x1: 1000, playheadT: 600, headAlpha: 1, refF0s: new Float32Array(0), ring })
    const dots = singing.fills.filter((f) => f.color === '#e07a3f')
    expect(dots).toHaveLength(1)
    expect(dots[0].radius).toBe(3)
  })
})

describe('live-chart · scoreColorOf（读数颜色：低分暖橙 → 中分青 → 高分绿）', () => {
  it('null → 中性灰；0/50/100 命中三个锚点色', () => {
    expect(scoreColorOf(null)).toBe('#999999')
    expect(scoreColorOf(0)).toBe('rgb(176,106,59)')
    expect(scoreColorOf(50)).toBe('rgb(44,127,143)')
    expect(scoreColorOf(100)).toBe('rgb(31,122,77)')
  })

  it('越界值被夹到 0~100；中间值连续（不跳变）', () => {
    expect(scoreColorOf(-20)).toBe(scoreColorOf(0))
    expect(scoreColorOf(180)).toBe(scoreColorOf(100))
    const a = scoreColorOf(60)
    const b = scoreColorOf(61)
    expect(a).not.toBe(b)
  })
})