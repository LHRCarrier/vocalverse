/**
 * 实时音高引擎（Worker 侧编排；**零 DOM 依赖**，可直接单测）。
 *
 * 职责：init(sampleRate) 一次性建复用缓冲的 YIN 检测器；tick(pcm,tMs) 出帧（或 null=静音）
 * + 节流后的实时分快照。每 tick 都记分（静音也记：出声率需要「参考有声但我没唱」的信息）。
 *
 * 线程模型（2026-09-18 性能改造）：主线程只做 AnalyserNode 拷窗 + transfer，
 * 重 DSP（差分累积 ~116 万次乘加/帧）全部在本模块运行的 Worker 里，主线程不再被阻塞。
 *
 * 消息协议也在此定义（worker 与主线程共用类型，worker 文件保持"薄适配器"）。
 */
import { createLiveScore, refF0AtMs, type LiveScore, type LiveScoreRead } from '@/lib/live-score'
import { centOf, createYinDetector, midiOf, noteNameOf, type YinDetector } from '@/lib/yin'

export interface PitchFrameOut {
  /** 相对录音起点（t0）的毫秒 */
  tMs: number
  f0: number
  midi: number
  note: string
  /** 相对最近半音的 cent（±50 内） */
  cent: number
}

/** 实时分回传节流（≤4Hz；分数是慢变量，避免 DOM 每 tick 抖动） */
const SCORE_EMIT_MS = 250

/** 主线程 → Worker */
export type PitchWorkerIn =
  | { type: 'init'; sampleRate: number }
  /** 参考旋律（按 32ms 槽压平的 f0s；null = 暂无参考） */
  | { type: 'ref'; f0s: Float32Array | null }
  /** pcm 以 transfer 送入；Worker 原样 transfer 回（主线程 buffer 池复用） */
  | { type: 'pcm'; pcm: Float32Array; tMs: number }
  | { type: 'stop' }

/** Worker → 主线程（每 tick 一条；score 仅在节流点非空） */
export type PitchWorkerOut =
  | { type: 'frame'; frame: PitchFrameOut; score: LiveScoreRead | null; pcm: Float32Array }
  | { type: 'silent'; score: LiveScoreRead | null; pcm: Float32Array }

export interface PitchTickResult {
  frame: PitchFrameOut | null
  score: LiveScoreRead | null
}

export interface PitchEngine {
  readonly sampleRate: number | null
  init: (sampleRate: number) => void
  setRef: (f0s: Float32Array | null) => void
  tick: (pcm: Float32Array, tMs: number) => PitchTickResult
}

export function createPitchEngine(): PitchEngine {
  let detector: YinDetector | null = null
  let sampleRate: number | null = null
  let ref: Float32Array | null = null
  let score: LiveScore | null = null
  let lastScoreMs = Number.NEGATIVE_INFINITY
  return {
    get sampleRate() {
      return sampleRate
    },
    init(sr) {
      sampleRate = sr
      detector = createYinDetector(sr, 2048)
      ref = null
      score = createLiveScore()
      lastScoreMs = Number.NEGATIVE_INFINITY
    },
    setRef(f0s) {
      ref = f0s
    },
    tick(pcm, tMs) {
      if (!detector || !score) return { frame: null, score: null }
      const r = detector.detect(pcm)
      score.add(tMs, refF0AtMs(ref, tMs), r?.f0 ?? 0)
      let outScore: LiveScoreRead | null = null
      if (tMs - lastScoreMs >= SCORE_EMIT_MS) {
        lastScoreMs = tMs
        outScore = score.read(tMs)
      }
      if (!r) return { frame: null, score: outScore }
      const midi = midiOf(r.f0)
      return {
        frame: { tMs, f0: r.f0, midi, note: noteNameOf(midi), cent: centOf(r.f0, midi) },
        score: outScore,
      }
    },
  }
}