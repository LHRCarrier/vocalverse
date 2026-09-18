/**
 * 轻量 YIN 基频检测（实时音准线用 · docs/06 §9.4 唱歌域 65~800Hz 与离线 pyin 同域）。
 *
 * 实现：de Cheveigné & Kawahara (2002) —— 差分累积 d' → CMNDF 归一化 →
 * 阈值（0.1）后首个局部谷 → 抛物线插值细分。纯函数、零依赖、可单测；
 * 帧级输入由调用方切窗（实际窗 2048@44.1/48k ≈ 42~46ms，覆盖 65Hz 周期 ≥2 个）。
 *
 * 口径注记（docs/06 §9.4）：实时线为**练习辅助**（"看得见的修正"），
 * 最终评分仍以离线 librosa.pyin + DTW 为准——同一音高域保证读数与评分可比，但不共用。
 */

export const YIN_MIN_HZ = 65
export const YIN_MAX_HZ = 800
export const YIN_THRESHOLD = 0.1

export interface YinResult {
  f0: number
  /** 1 - CMNDF 谷值（越接近 1 越自信；浊音判据 = 存在低于阈值的谷） */
  confidence: number
}

/**
 * 单窗 YIN 检测；无法给出可信基频（静音/低信噪比/非周期）→ null。
 * @param samples 时域 float 窗（长度 ≥ 2×65Hz 周期）
 */
export function detectPitch(
  samples: Float32Array,
  sampleRate: number,
  threshold: number = YIN_THRESHOLD,
): YinResult | null {
  const n = samples.length
  const tauMax = Math.min(Math.floor(n / 2), Math.floor(sampleRate / YIN_MIN_HZ))
  const tauMin = Math.max(2, Math.floor(sampleRate / YIN_MAX_HZ))
  if (tauMax <= tauMin) return null
  return yinCore(samples, sampleRate, tauMax, tauMin, new Float64Array(tauMax + 1), new Float64Array(tauMax + 1), threshold)
}

/**
 * 复用缓冲的 YIN 检测器（实时链路每 tick 调用，**零分配**）。
 *
 * 2026-09-18 性能改造：旧实现每帧调用 detectPitch → 每次新建 2 个 (tauMax+1)≈679 长
 * Float64Array（16.7 次/秒×2），在真机上表现为周期性 GC 抖动（基线见 local/sing-bench-before-*.json）。
 * 本检测器一次性分配 d/cmndf，检测结果与 detectPitch **逐位一致**（同一 yinCore）。
 */
export interface YinDetector {
  /** 检测窗长（采样点） */
  readonly n: number
  /** 差分 tau 上界（= 最低音约束，同时决定缓冲长度） */
  readonly tauMax: number
  /** 内部缓冲（测试/调试用：证明跨次复用而非重建） */
  readonly buffers: { d: Float64Array; cmndf: Float64Array }
  detect: (samples: Float32Array) => YinResult | null
}

export function createYinDetector(
  sampleRate: number,
  n = 2048,
  threshold: number = YIN_THRESHOLD,
): YinDetector {
  const tauMax = Math.min(Math.floor(n / 2), Math.floor(sampleRate / YIN_MIN_HZ))
  const tauMin = Math.max(2, Math.floor(sampleRate / YIN_MAX_HZ))
  const d = new Float64Array(Math.max(0, tauMax + 1))
  const cmndf = new Float64Array(Math.max(0, tauMax + 1))
  return {
    n,
    tauMax,
    buffers: { d, cmndf },
    detect: (samples) => yinCore(samples, sampleRate, tauMax, tauMin, d, cmndf, threshold),
  }
}

/** 差分累积 → CMNDF → 阈值首谷 → 抛物线插值（detectPitch 与 createYinDetector 共用） */
function yinCore(
  samples: Float32Array,
  sampleRate: number,
  tauMax: number,
  tauMin: number,
  d: Float64Array,
  cmndf: Float64Array,
  threshold: number,
): YinResult | null {
  const n = samples.length
  if (tauMax <= tauMin) return null

  // ① 差分累积 d'(tau)（论文式(1)）
  for (let tau = 1; tau <= tauMax; tau += 1) {
    let sum = 0
    const lim = n - tau
    for (let i = 0; i < lim; i += 1) {
      const diff = samples[i] - samples[i + tau]
      sum += diff * diff
    }
    d[tau] = sum
  }

  // ② CMNDF 归一化（论文式(4)）
  cmndf[0] = 1
  let running = 0
  for (let tau = 1; tau <= tauMax; tau += 1) {
    running += d[tau]
    cmndf[tau] = running > 0 ? (d[tau] * tau) / running : 1
  }

  // ③ 阈值[0,1)后的首个局部谷（论文式(6)；先压低到谷底再跳出）
  let tau = -1
  for (let t = tauMin; t <= tauMax; t += 1) {
    if (cmndf[t] >= threshold) continue
    tau = t
    while (tau + 1 <= tauMax && cmndf[tau + 1] < cmndf[tau]) tau += 1
    break
  }
  if (tau < 0) return null

  // ④ 抛物线插值细分（论文式(7)）
  let betterTau = tau
  if (tau > 1 && tau < tauMax) {
    const s0 = cmndf[tau - 1]
    const s1 = cmndf[tau]
    const s2 = cmndf[tau + 1]
    const denom = 2 * (2 * s1 - s2 - s0)
    if (denom !== 0) betterTau = tau + (s2 - s0) / denom
  }
  const f0 = sampleRate / betterTau
  if (f0 < YIN_MIN_HZ || f0 > YIN_MAX_HZ) return null
  return { f0, confidence: 1 - cmndf[tau] }
}

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

/** Hz → 最近半音 MIDI（与后端 pitch.py 同口径：round(69 + 12·log2(f/440))，docs/06 §9.4） */
export function midiOf(f0: number): number {
  return Math.round(69 + 12 * Math.log2(f0 / 440))
}

/** MIDI → 音名（A4=69） */
export function noteNameOf(midi: number): string {
  const m = ((Math.round(midi) % 12) + 12) % 12
  return `${NOTE_NAMES[m]}${Math.floor(midi / 12) - 1}`
}

/** 相对最近半音的 cent 偏差（±50 内；+ = 偏高） */
export function centOf(f0: number, midi: number): number {
  const ref = 440 * 2 ** ((Math.round(midi) - 69) / 12)
  return 1200 * Math.log2(f0 / ref)
}
