/**
 * 实时音准线 · 绘制侧纯逻辑（docs/06 §9.4 注记：练习辅助）。
 *
 * 从 LivePitchChart 下沉的三块热路径逻辑（组件只留编排）：
 * ① 参考旋律压平：逐句 pitch_ref.f0s → 全曲时间轴 Float32Array（索引 = tMs/32ms），
 *    供「按可见窗取点」绘制与实时分比对，避免每帧遍历整曲句数组；
 * ② 用户帧环形缓冲：两个 Float64Array（tMs/f0）交替，**零分配零响应式代理**
 *    （旧实现每帧 `[...frames]` 重建 + 逐点走 Vue proxy，见 2026-09-18 性能基线）；
 * ③ 可见窗二分 + 全帧绘制（renderChart）：只画窗内点，末尾点按静音时长淡出。
 *
 * 口径与后端一致：hop 512@16k = 32ms（services/python app/audio/pitch.py）。
 */
import type { SongDetail } from '@/api/sing'

/** 参考旋律 hop（与后端 pyin hop 512@16k=32ms 同口径，docs/06 §9.4） */
export const REF_HOP_MS = 32

/** 视口宽（滚动时间窗，ms） */
export const WIN_MS = 8000
/** 视口右端前瞻（ms；当前时刻右侧留白，便于看到最新点） */
export const LOOKAHEAD_MS = 500
/** 纵轴音高域（Hz；与离线评分同域） */
const FMIN = 65
const FMAX = 800
/** 纵轴每八度网格标签（C3~C6） */
const NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

/**
 * 把逐句参考旋律压平成全曲时间轴（0 = 无声/缺失）。
 * 句内第 i 点位于 `line.start_ms + i*REF_HOP_MS`；句间空隙自然为 0（断笔）。
 */
export function flattenRefF0s(detail: SongDetail): Float32Array {
  let end = 0
  for (const line of detail.lines) {
    const n = line.pitch_ref?.f0s?.length ?? 0
    if (!n) continue
    const e = Math.round((line.start_ms ?? 0) / REF_HOP_MS) + n
    if (e > end) end = e
  }
  const out = new Float32Array(end)
  for (const line of detail.lines) {
    const f0s = line.pitch_ref?.f0s
    if (!f0s?.length) continue
    const start = Math.round((line.start_ms ?? 0) / REF_HOP_MS)
    for (let i = 0; i < f0s.length; i += 1) {
      const idx = start + i
      if (idx >= 0 && idx < out.length) out[idx] = f0s[i]
    }
  }
  return out
}

/** 参考音高查询（Hz；0 = 该时刻参考无声）。越界返回 0。 */
export function refF0At(ref: Float32Array, tMs: number): number {
  if (!ref.length) return 0
  const i = Math.round(tMs / REF_HOP_MS)
  return i >= 0 && i < ref.length ? ref[i] : 0
}

/** 用户帧环形缓冲（tMs 必须单调不减；满员覆盖最旧） */
export interface FrameRing {
  readonly capacity: number
  length: () => number
  push: (tMs: number, f0: number) => void
  clear: () => void
  tAt: (i: number) => number
  fAt: (i: number) => number
  /** 第一个 tMs >= t 的逻辑下标；不存在返回 length() */
  lowerBound: (t: number) => number
}

export function createFrameRing(capacity: number): FrameRing {
  const cap = Math.max(1, Math.floor(capacity))
  const ts = new Float64Array(cap)
  const f0s = new Float64Array(cap)
  /** 逻辑 0 所在物理下标（覆盖满后前移） */
  let head = 0
  let n = 0
  const phys = (i: number) => (head + i) % cap
  return {
    capacity: cap,
    length: () => n,
    push(tMs, f0) {
      const p = n < cap ? phys(n) : head
      ts[p] = tMs
      f0s[p] = f0
      if (n < cap) n += 1
      else head = (head + 1) % cap
    },
    clear() {
      head = 0
      n = 0
    },
    tAt: (i) => ts[phys(i)],
    fAt: (i) => f0s[phys(i)],
    lowerBound(t) {
      let lo = 0
      let hi = n
      while (lo < hi) {
        const mid = (lo + hi) >> 1
        if (ts[phys(mid)] < t) lo = mid + 1
        else hi = mid
      }
      return lo
    },
  }
}

// —— 绘制（组件给几何与淡出系数；本模块只画，不持有响应式状态/定时器）——

/** 停摆淡出时单独降透明度的末尾点数 */
const FADE_PTS = 6

export interface ChartFrame {
  /** 逻辑宽高（CSS px；调用方已按 dpr setTransform） */
  w: number
  h: number
  /** 视口右端时间（ms） */
  x1: number
  /** 进度竖线时间（ms；一般 = 当前锚点） */
  playheadT: number
  /** 末尾点淡出系数（0~1；1 = 不淡出） */
  headAlpha: number
  refF0s: Float32Array
  ring: FrameRing
}

function drawGrid(g: CanvasRenderingContext2D, w: number, y2f: (f: number) => number) {
  g.font = '9px sans-serif'
  g.strokeStyle = 'rgba(0,0,0,.08)'
  g.fillStyle = '#6b6f6e'
  for (let midi = 48; midi <= 84; midi += 12) {
    const y = y2f(440 * 2 ** ((midi - 69) / 12))
    g.beginPath()
    g.moveTo(4, y)
    g.lineTo(w - 4, y)
    g.stroke()
    g.fillText(`${NAMES[midi % 12]}${Math.floor(midi / 12) - 1}`, 6, y - 2)
  }
}

/** 参考线：只画可见窗内的压平点（旧实现每帧遍历整曲句数组 ≈5625 点） */
function drawRefLine(
  g: CanvasRenderingContext2D,
  refF0s: Float32Array,
  w: number,
  x0: number,
  x1: number,
  x2p: (t: number) => number,
  y2f: (f: number) => number,
) {
  const len = refF0s.length
  if (!len) return
  g.strokeStyle = '#3a8fb7'
  g.lineWidth = 1.6
  g.globalAlpha = 0.9
  const i0 = Math.max(0, Math.floor(x0 / REF_HOP_MS) - 1)
  const i1 = Math.min(len - 1, Math.ceil(x1 / REF_HOP_MS) + 1)
  g.beginPath()
  let started = false
  for (let i = i0; i <= i1; i += 1) {
    const f = refF0s[i]
    if (f <= 0) {
      started = false
      continue
    }
    const px = x2p(i * REF_HOP_MS)
    if (px < 4 || px > w - 4) continue
    if (!started) {
      g.moveTo(px, y2f(f))
      started = true
    } else {
      g.lineTo(px, y2f(f))
    }
  }
  g.stroke()
  g.globalAlpha = 1
}

/** 用户轨迹：二分可见窗 + 末尾点静音淡出（仅透明度，符合 docs/31） */
function drawUserTrace(
  g: CanvasRenderingContext2D,
  ring: FrameRing,
  x0: number,
  x1: number,
  x2p: (t: number) => number,
  y2f: (f: number) => number,
  headAlpha: number,
) {
  const n = ring.length()
  if (!n) return
  const i0 = ring.lowerBound(x0)
  const i1 = ring.lowerBound(x1)
  if (i1 <= i0) return
  g.strokeStyle = '#e07a3f'
  g.lineWidth = 1.8
  const tailFrom = headAlpha < 1 ? Math.max(i0, i1 - FADE_PTS) : i1
  g.beginPath()
  let started = false
  for (let i = i0; i < tailFrom; i += 1) {
    const px = x2p(ring.tAt(i))
    const py = y2f(ring.fAt(i))
    if (!started) {
      g.moveTo(px, py)
      started = true
    } else {
      g.lineTo(px, py)
    }
  }
  g.stroke()
  if (tailFrom < i1) {
    let prevX = NaN
    let prevY = NaN
    if (tailFrom > i0) {
      prevX = x2p(ring.tAt(tailFrom - 1))
      prevY = y2f(ring.fAt(tailFrom - 1))
    }
    for (let i = tailFrom; i < i1; i += 1) {
      const px = x2p(ring.tAt(i))
      const py = y2f(ring.fAt(i))
      g.globalAlpha = headAlpha * ((i1 - i) / (i1 - tailFrom + 1))
      g.beginPath()
      if (Number.isNaN(prevX)) {
        g.moveTo(px, py)
      } else {
        g.moveTo(prevX, prevY)
        g.lineTo(px, py)
      }
      g.stroke()
      prevX = px
      prevY = py
    }
    g.globalAlpha = 1
  }
  const li = i1 - 1
  const lt = ring.tAt(li)
  if (lt >= x0 && lt <= x1) {
    g.fillStyle = '#e07a3f'
    g.globalAlpha = headAlpha
    g.beginPath()
    g.arc(x2p(lt), y2f(ring.fAt(li)), 3, 0, Math.PI * 2)
    g.fill()
    g.globalAlpha = 1
  }
}

/** 画一帧（网格 + 参考线 + 用户轨迹 + 进度竖线） */
export function renderChart(g: CanvasRenderingContext2D, f: ChartFrame): void {
  const { w, h, x1, playheadT, headAlpha, refF0s, ring } = f
  const x0 = x1 - WIN_MS
  const x2p = (t: number) => 4 + ((t - x0) / WIN_MS) * (w - 8)
  const logFmin = Math.log2(FMIN)
  const y2f = (fq: number) => 6 + (1 - (Math.log2(fq) - logFmin) / (Math.log2(FMAX) - logFmin)) * (h - 24)

  drawGrid(g, w, y2f)
  drawRefLine(g, refF0s, w, x0, x1, x2p, y2f)
  drawUserTrace(g, ring, x0, x1, x2p, y2f, headAlpha)

  g.strokeStyle = 'rgba(0,0,0,.25)'
  g.lineWidth = 1
  const px = x2p(Math.min(playheadT, x1))
  g.beginPath()
  g.moveTo(px, 6)
  g.lineTo(px, h - 14)
  g.stroke()
}