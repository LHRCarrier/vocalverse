/**
 * 音符引导条（2026-09-22 深色录唱页新增，对齐参考图「橙色横条」）：数据派生 + 渲染。
 *
 * 数据源：`SongDetail.lines[].pitch_ref.{midi,f0s}`（离线 pyin 提取，与评分同源）。
 * 为什么用 midi 而不是 f0s 画条：参考图画的是**目标音符块**（一个个音高台阶），
 * midi 逐帧序列按「连续同值」切段天然就是这些块；f0s 还要自己量化到音名。
 *
 * 与 `live-chart.ts` 的关系：那里管实时检测（Worker/环形缓冲/静音灰线），本模块只管
 * 「把参考音符 + 用户实时轨迹画成一条引导带」；`REF_HOP_MS` 等常量复用同一口径（32ms/帧）。
 */
import { REF_HOP_MS } from './live-chart'
import type { SongDetail } from '@/api/sing'

/** 无音高（清音帧/缺数据）在 midi 轨里的占位值 */
export const NO_MIDI = -1
/** 单个音符块最短时长（ms）：更短的碎块归并进前一块，避免画面全是细缝 */
export const MIN_SEGMENT_MS = 96

export interface NoteSegment {
  /** 相对歌曲开头的起止（ms） */
  startMs: number
  endMs: number
  /** MIDI 音高（整数；同一块内恒定） */
  midi: number
}

/**
 * 逐句 `pitch_ref.midi` → 整曲逐帧 MIDI 轨（Float32Array，hop = `REF_HOP_MS`）。
 * 与 `flattenRefF0s` 同构：按 `line.start_ms` 定位写入，未覆盖处 = `NO_MIDI`。
 */
export function flattenRefMidi(detail: SongDetail): Float32Array {
  const lines = detail.lines ?? []
  let endMs = 0
  for (const l of lines) {
    const len = l.pitch_ref?.midi?.length ?? 0
    if (len) endMs = Math.max(endMs, (l.start_ms ?? 0) + len * REF_HOP_MS)
  }
  const total = Math.ceil(endMs / REF_HOP_MS) + 1
  const out = new Float32Array(total).fill(NO_MIDI)
  for (const l of lines) {
    const midi = l.pitch_ref?.midi
    if (!midi?.length) continue
    const base = Math.floor((l.start_ms ?? 0) / REF_HOP_MS)
    for (let i = 0; i < midi.length; i += 1) {
      const v = midi[i]
      const idx = base + i
      if (idx >= 0 && idx < total) out[idx] = v == null ? NO_MIDI : v
    }
  }
  return out
}

/**
 * 逐帧 MIDI → 音符块（纯函数）：连续同值帧合成一段，`NO_MIDI` 断开；
 * 短于 `minMs` 的碎块归并到前一块（有前块时顺延其结束时间），避免视觉抖动。
 */
export function midiSegments(
  midi: Float32Array,
  hopMs: number = REF_HOP_MS,
  minMs: number = MIN_SEGMENT_MS,
): NoteSegment[] {
  const segs: NoteSegment[] = []
  let cur: NoteSegment | null = null
  for (let i = 0; i < midi.length; i += 1) {
    const v = midi[i]
    const t = i * hopMs
    if (v === NO_MIDI || v < 0) {
      if (cur) {
        segs.push(cur)
        cur = null
      }
      continue
    }
    if (cur && cur.midi === v) {
      cur.endMs = t + hopMs
      continue
    }
    if (cur) segs.push(cur)
    cur = { startMs: t, endMs: t + hopMs, midi: v }
  }
  if (cur) segs.push(cur)

  // 归并过短块：并入前一块（没有前块则并入后一块）
  const out: NoteSegment[] = []
  for (const s of segs) {
    const prev = out[out.length - 1]
    if (s.endMs - s.startMs < minMs) {
      if (prev) prev.endMs = s.endMs
      else if (segs.length > 1) continue // 首块太短且后面还有 → 丢弃
      else out.push(s)
      continue
    }
    out.push(s)
  }
  // 归并可能让相邻同音块首尾相接 → 再合一次
  const merged: NoteSegment[] = []
  for (const s of out) {
    const prev = merged[merged.length - 1]
    if (prev && prev.midi === s.midi && s.startMs - prev.endMs <= hopMs) prev.endMs = s.endMs
    else merged.push({ ...s })
  }
  return merged
}

/* ---------------- 渲染（深色引导带） ---------------- */

/** 深色引导带配色（与参考图同调：橙色目标块 + 青色用户轨迹） */
const LANE = {
  bg: '#131b20',
  gridLine: 'rgba(255,255,255,.06)',
  gridText: 'rgba(255,255,255,.32)',
  note: '#f5a524',
  noteActive: '#ffc83d',
  playhead: 'rgba(255,255,255,.75)',
  user: '#5ad2c0',
  userHead: '#8ff0e2',
  silent: 'rgba(255,255,255,.18)',
}
const NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

export interface NoteLaneFrame {
  /** 逻辑宽高（CSS px；调用方已按 dpr setTransform） */
  w: number
  h: number
  /** 视口右端时间（ms） */
  x1: number
  /** 走针时间（ms）= 当前锚点 */
  playheadT: number
  /** 视口宽度（ms）：左端 = x1 - windowMs */
  windowMs: number
  /** 整曲逐帧 MIDI（`flattenRefMidi`） */
  refMidi: Float32Array
  /** 音符块（`midiSegments`，调用方缓存；避免每帧重算） */
  segments: NoteSegment[]
  /** 用户轨迹点（t = 数据时间 ms） */
  userPoints: { t: number; midi: number }[]
  /** 末尾点淡出（0~1） */
  headAlpha?: number
  /** 暂停中：走针不变灰但整带降亮，表达「已冻结」 */
  paused?: boolean
}

const midiToY = (midi: number, h: number) => {
  const lo = 48 // C3
  const hi = 84 // C6
  const m = Math.min(hi, Math.max(lo, midi))
  return h - 10 - ((m - lo) / (hi - lo)) * (h - 24)
}

/** 网格 + 音名（八度实线，半音淡线） */
function drawLaneGrid(g: CanvasRenderingContext2D, w: number, h: number): void {
  g.font = '9px sans-serif'
  g.lineWidth = 1
  g.strokeStyle = LANE.gridLine
  g.fillStyle = LANE.gridText
  for (let midi = 48; midi <= 84; midi += 12) {
    const y = Math.round(midiToY(midi, h)) + 0.5
    g.beginPath()
    g.moveTo(0, y)
    g.lineTo(w, y)
    g.stroke()
    g.fillText(`${NAMES[midi % 12]}${Math.floor(midi / 12) - 1}`, 6, y - 3)
  }
  g.strokeStyle = 'rgba(255,255,255,.03)'
  for (let midi = 48; midi <= 84; midi += 1) {
    if (midi % 12 === 0) continue
    const y = Math.round(midiToY(midi, h)) + 0.5
    g.beginPath()
    g.moveTo(0, y)
    g.lineTo(w, y)
    g.stroke()
  }
}

/** 目标音符块（橙色圆角横条；正在唱的块提亮）。只画可见窗内的块（整曲几百块） */
function drawNotes(
  g: CanvasRenderingContext2D,
  f: NoteLaneFrame,
  t2x: (t: number) => number,
): void {
  const { h, x1, playheadT } = f
  const x0 = x1 - f.windowMs
  const barH = Math.max(6, Math.min(14, (h - 24) / 30))
  const rad = barH / 2
  for (const s of f.segments) {
    if (s.endMs < x0 || s.startMs > x1) continue
    const active = playheadT >= s.startMs && playheadT <= s.endMs
    const x = t2x(s.startMs)
    const bw = Math.max(2, t2x(s.endMs) - x)
    const y = midiToY(s.midi, h) - barH / 2
    g.fillStyle = active ? LANE.noteActive : LANE.note
    g.globalAlpha = (f.paused ? 0.55 : 1) * (active ? 1 : 0.82)
    g.beginPath()
    g.moveTo(x + rad, y)
    g.lineTo(x + bw - rad, y)
    g.arcTo(x + bw, y, x + bw, y + rad, rad)
    g.lineTo(x + bw, y + barH - rad)
    g.arcTo(x + bw, y + barH, x + bw - rad, y + barH, rad)
    g.lineTo(x + rad, y + barH)
    g.arcTo(x, y + barH, x, y + barH - rad, rad)
    g.lineTo(x, y + rad)
    g.arcTo(x, y, x + rad, y, rad)
    g.closePath()
    g.fill()
  }
  g.globalAlpha = f.paused ? 0.55 : 1
}

/** 用户轨迹（青色细线 + 头点淡出）+ 走针 */
function drawUserAndPlayhead(
  g: CanvasRenderingContext2D,
  f: NoteLaneFrame,
  t2x: (t: number) => number,
): void {
  const { h, w, x1, playheadT } = f
  const x0 = x1 - f.windowMs
  const pts = f.userPoints
  if (pts.length > 1) {
    g.strokeStyle = LANE.user
    g.lineWidth = 1.8
    g.lineJoin = 'round'
    g.beginPath()
    let started = false
    for (const p of pts) {
      if (p.t < x0 - 50 || p.t > x1) continue
      const x = t2x(p.t)
      const y = midiToY(p.midi, h)
      if (!started) {
        g.moveTo(x, y)
        started = true
      } else g.lineTo(x, y)
    }
    if (started) g.stroke()
  }
  const last = pts[pts.length - 1]
  if (last && last.t >= x0 && last.t <= x1 && (f.headAlpha ?? 1) > 0) {
    g.globalAlpha = (f.paused ? 0.55 : 1) * (f.headAlpha ?? 1)
    g.fillStyle = LANE.userHead
    g.beginPath()
    g.arc(t2x(last.t), midiToY(last.midi, h), 3.2, 0, Math.PI * 2)
    g.fill()
    g.globalAlpha = f.paused ? 0.55 : 1
  }
  const px = Math.round(t2x(playheadT)) + 0.5
  if (px >= 0 && px <= w) {
    g.strokeStyle = LANE.playhead
    g.lineWidth = 1.5
    g.beginPath()
    g.moveTo(px, 6)
    g.lineTo(px, h - 6)
    g.stroke()
  }
}

/**
 * 画一条引导带：底 + 音名网格 + 目标音符块（橙色圆角条）+ 用户轨迹（青色细线）+ 走针竖线。
 */
export function renderNoteLane(g: CanvasRenderingContext2D, f: NoteLaneFrame): void {
  const { w, h, x1, windowMs } = f
  const x0 = x1 - windowMs
  const t2x = (t: number) => ((t - x0) / windowMs) * w
  g.clearRect(0, 0, w, h)
  g.fillStyle = LANE.bg
  g.fillRect(0, 0, w, h)
  g.globalAlpha = f.paused ? 0.55 : 1
  drawLaneGrid(g, w, h)
  drawNotes(g, f, t2x)
  drawUserAndPlayhead(g, f, t2x)
  g.globalAlpha = 1
}
