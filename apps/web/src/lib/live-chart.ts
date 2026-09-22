/**
 * 实时音准线 · 绘制侧纯逻辑（docs/06 §9.4 注记：练习辅助）。
 *
 * 从 LivePitchChart 下沉的三块热路径逻辑（组件只留编排）：
 * ① 参考旋律压平：逐句 pitch_ref.f0s → 全曲时间轴 Float32Array（索引 = tMs/32ms），
 *    供「按可见窗取点」绘制与实时分比对，避免每帧遍历整曲句数组；
 * ② 用户帧环形缓冲：两个 Float64Array（tMs/f0）交替，**零分配零响应式代理**
 *    （旧实现每帧 `[...frames]` 重建 + 逐点走 Vue proxy，见 2026-09-18 性能基线）；
 * ③ 可见窗二分 + 全帧绘制（renderChart）：只画窗内点，末尾点按静音时长淡出；
 *    **没出声的时间段用底部灰线表示**（eachSilenceSpan → drawSilenceLine，2026-09-18 需求）。
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

/**
 * 用户音高按**八度等价**对齐到参考（**显示口径** · 2026-09-22 用户报「怎么唱都不在块内」）：
 * 离线评分本就是八度等价（`_fold_cent` 折叠到 ±600 cent + v3 移调补偿，KTV/唱吧同口径），
 * 而实时轨迹此前按**绝对频率**画 → 男声唱女声歌（或反之）整条轨迹落在目标音符块外一个八度，
 * 用户看到的反馈就是「怎么唱都不在块内」。这里取最近的整数八度平移
 * （k = round(log2(ref/f0))），让轨迹落回块内；无参考（refF ≤ 0）时不平移。
 */
export function octaveShift(f0: number, refF: number): number {
  if (f0 <= 0 || refF <= 0) return 0
  return Math.round(Math.log2(refF / f0))
}

/** 便捷式：把用户音高平移 {@link octaveShift} 个八度（无参考时原样返回）。 */
export function octaveAlignedF0(f0: number, refF: number): number {
  const oct = octaveShift(f0, refF)
  return oct === 0 ? f0 : f0 * 2 ** oct
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

/** 静音灰线：判据（相邻浊音帧间隔超过它才算「没在唱」，≈3 个检测 tick） */
export const SILENCE_GAP_MS = 300
/** 静音灰线：位置（画布底部、低于 65Hz 轴下限，避免与最低音混淆） */
const SILENCE_Y_OFFSET = 9
const SILENCE_COLOR = '#b9bdbc'

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
  /**
   * 头部插值点（2026-09-18 平滑）：新帧到达后由调用方在 ~90ms 内把头部从上一位置插值到新帧值，
   * **只影响最后一段**，历史曲线仍是原始采样值（不掩盖音高抖动）；null = 用原始末点。
   */
  head?: HeadPoint | null
}

/** 头部插值点（t = 数据时间 ms；f = Hz；插值在 log 域做，屏幕上即线性） */
export interface HeadPoint {
  t: number
  f: number
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

/**
 * 用户轨迹：二分可见窗 + 折线圆角化 + 头部插值。
 *
 * 静音语义（2026-09-21 调整）：**静音段不画橙线**——橙色轨迹在「最后一次出声」处干净结束，
 * 之后交给底部灰线（{@link drawSilenceLine}）。原先"末尾 N 点渐隐"会在停唱位置留下一个
 * 淡不干净的橙点，现已去掉；只保留**头部圆点**随静音时长淡出到 0（无残留）。
 *
 * 音高语义（2026-09-22）：每个点先经 {@link octaveAlignedF0} 对齐到参考的八度
 * （与离线评分同口径）——否则差一个八度时整条轨迹画在块外，用户看着像「唱不进去」。
 */
function drawUserTrace(
  g: CanvasRenderingContext2D,
  ring: FrameRing,
  refF0s: Float32Array,
  x0: number,
  x1: number,
  x2p: (t: number) => number,
  y2f: (f: number) => number,
  headAlpha: number,
  head: HeadPoint | null,
) {
  const n = ring.length()
  if (!n) return
  const i0 = ring.lowerBound(x0)
  const i1 = ring.lowerBound(x1)
  if (i1 <= i0) return
  g.strokeStyle = '#e07a3f'
  g.lineWidth = 1.8
  // 中点二次贝塞尔圆角化（消锯齿折角）：历史点用原始采样值，仅末点可被 head 插值替换
  g.beginPath()
  let started = false
  let cx = 0
  let cy = 0
  const push = (x: number, y: number) => {
    if (!started) {
      g.moveTo(x, y)
      started = true
    } else {
      g.quadraticCurveTo(cx, cy, (cx + x) / 2, (cy + y) / 2)
    }
    cx = x
    cy = y
  }
  /** 八度偏移**随最近一次有参考的点保持**：句间空隙/前奏处参考缺失时不来回跳 */
  let oct = 0
  const alignedY = (t: number, f0: number) => {
    const refF = refF0At(refF0s, t)
    if (f0 > 0 && refF > 0) oct = octaveShift(f0, refF)
    return y2f(oct === 0 ? f0 : f0 * 2 ** oct)
  }
  for (let i = i0; i < i1; i += 1) {
    const t = ring.tAt(i)
    push(x2p(t), alignedY(t, ring.fAt(i)))
  }
  const lastI = i1 - 1
  const headT = head ? head.t : ring.tAt(lastI)
  const headF = head ? head.f : ring.fAt(lastI)
  const headIn = headT >= x0 && headT <= x1
  if (headIn) push(x2p(headT), alignedY(headT, headF))
  if (started) {
    g.lineTo(cx, cy) // 收尾：二次贝塞尔只画到中点，需补到最后一个顶点
  }
  g.stroke()
  // 头部圆点：静音后随 headAlpha 淡出到 0（< 0.02 直接不画，避免残留）
  if (headIn && headAlpha > 0.02) {
    g.fillStyle = '#e07a3f'
    g.globalAlpha = headAlpha
    g.beginPath()
    g.arc(x2p(headT), alignedY(headT, headF), 3, 0, Math.PI * 2)
    g.fill()
    g.globalAlpha = 1
  }
}

/** 画一帧（网格 + 静音灰线 + 参考线 + 用户轨迹 + 进度竖线） */
export function renderChart(g: CanvasRenderingContext2D, f: ChartFrame): void {
  const { w, h, x1, playheadT, headAlpha, refF0s, ring, head } = f
  const x0 = x1 - WIN_MS
  const x2p = (t: number) => 4 + ((t - x0) / WIN_MS) * (w - 8)
  const logFmin = Math.log2(FMIN)
  const y2f = (fq: number) => 6 + (1 - (Math.log2(fq) - logFmin) / (Math.log2(FMAX) - logFmin)) * (h - 24)

  drawGrid(g, w, y2f)
  drawSilenceLine(g, ring, x0, x1, playheadT, x2p, h)
  drawRefLine(g, refF0s, w, x0, x1, x2p, y2f)
  drawUserTrace(g, ring, refF0s, x0, x1, x2p, y2f, headAlpha, head ?? null)

  g.strokeStyle = 'rgba(0,0,0,.25)'
  g.lineWidth = 1
  const px = x2p(Math.min(playheadT, x1))
  g.beginPath()
  g.moveTo(px, 6)
  g.lineTo(px, h - 14)
  g.stroke()
}

/**
 * 遍历「无浊音」时间段（2026-09-18 需求：没出声时也要有时间轴信息，用底部灰线表示「无音高」）。
 *
 * 三处来源：① 首个浊音帧之前（含录音开头未唱）② 相邻浊音帧之间的空隙 ③ 末帧之后仍在静音（延伸到 now）。
 * 每段按 [from, to] 视窗与 t>=0 裁剪，且长度须 > SILENCE_GAP_MS——正常换气/顿音（几十~两百毫秒）
 * 不会被误画成静音。纯计算、回调式（绘制热路径零数组分配），绘制见 {@link drawSilenceLine}。
 */
export function eachSilenceSpan(
  ring: FrameRing,
  from: number,
  to: number,
  now: number,
  fn: (a: number, b: number) => void,
): void {
  const add = (a: number, b: number) => {
    const s = Math.max(a, from, 0)
    const e = Math.min(b, to, now)
    if (e - s > SILENCE_GAP_MS) fn(s, e)
  }
  const n = ring.length()
  if (!n) {
    add(0, now)
    return
  }
  add(0, ring.tAt(0))
  for (let i = 1; i < n; i += 1) add(ring.tAt(i - 1), ring.tAt(i))
  add(ring.tAt(n - 1), now)
}

/** 静音段画成底部灰线（横线；用户轨迹在上方，不会与之混淆） */
function drawSilenceLine(
  g: CanvasRenderingContext2D,
  ring: FrameRing,
  x0: number,
  x1: number,
  now: number,
  x2p: (t: number) => number,
  h: number,
): void {
  const y = h - SILENCE_Y_OFFSET
  g.strokeStyle = SILENCE_COLOR
  g.lineWidth = 2
  g.beginPath()
  eachSilenceSpan(ring, x0, x1, now, (a, b) => {
    g.moveTo(x2p(a), y)
    g.lineTo(x2p(b), y)
  })
  g.stroke()
}

/**
 * 实时分 → 读数颜色（2026-09-18 读数动画）：低分暖橙 → 中分青 → 高分绿，**连续插值**，
 * 配合 CSS `transition: color` 平滑过渡；null（参考不足）→ 中性灰。
 */
export function scoreColorOf(score: number | null): string {
  if (score == null) return '#999999'
  const t = Math.max(0, Math.min(1, score / 100))
  const mix = (c1: number[], c2: number[], k: number) =>
    `rgb(${Math.round(c1[0] + (c2[0] - c1[0]) * k)},${Math.round(c1[1] + (c2[1] - c1[1]) * k)},${Math.round(
      c1[2] + (c2[2] - c1[2]) * k,
    )})`
  const low = [176, 106, 59]
  const mid = [44, 127, 143]
  const high = [31, 122, 77]
  return t < 0.5 ? mix(low, mid, t / 0.5) : mix(mid, high, (t - 0.5) / 0.5)
}