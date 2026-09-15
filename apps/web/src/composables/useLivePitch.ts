/**
 * 实时音高检测器（docs/06 §9.4 注记：练习辅助，评分以离线 pyin 为准）。
 *
 * 链路：同一 MediaStream（recorder.liveStream，不二次申请麦克风）→
 * AudioContext → AnalyserNode(fftSize 2048, 无平滑) → getFloatTimeDomainData →
 * 自写 YIN（lib/yin.ts）→ onFrame(音高/音名/±cent/时间戳)。
 *
 * 约定：
 * - 帧率 ~60ms（≈16fps 更新 + canvas rAF 独立渲染）；窗 2048@44.1/48k ≈ 42~46ms；
 * - start() 幂等（先停旧的）；stop() 断开并 close AudioContext（防泄漏）；
 * - YIN null（静音/噪声）不回调——UI 用「最近一帧到期」表达静音态；
 * - 时间戳 = start 后经过 ms（参考线 t0=录音开始，练习辅助口径，不做整首对齐）。
 */

import { detectPitch, midiOf, noteNameOf, centOf } from '@/lib/yin'

export interface LivePitchFrame {
  /** 相对检测起点（录音开始）的毫秒 */
  tMs: number
  f0: number
  midi: number
  note: string
  /** 相对最近半音的 cent（±50 内） */
  cent: number
}

export interface LivePitchHandles {
  start: (stream: MediaStream) => void
  stop: () => void
  readonly active: boolean
}

export function createLivePitch(
  onFrame: (frame: LivePitchFrame) => void,
  intervalMs: number = 60,
): LivePitchHandles {
  let ctx: AudioContext | null = null
  let source: MediaStreamAudioSourceNode | null = null
  let analyser: AnalyserNode | null = null
  let timer: ReturnType<typeof setInterval> | null = null
  let buf: Float32Array | null = null
  let t0 = 0
  let active = false

  function start(stream: MediaStream) {
    stop()
    try {
      const Ctor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      ctx = new Ctor()
      source = ctx.createMediaStreamSource(stream)
      analyser = ctx.createAnalyser()
      analyser.fftSize = 2048
      analyser.smoothingTimeConstant = 0
      source.connect(analyser)
      buf = new Float32Array(analyser.fftSize)
      t0 = performance.now()
      // 用户手势链内创建；resume 失败仅掉实时线，不阻塞录音（practice 辅助语义）
      void ctx.resume().catch(() => {})
      active = true
      const actx = ctx
      timer = setInterval(() => {
        if (!analyser || !buf || !actx) return
        analyser.getFloatTimeDomainData(buf)
        const r = detectPitch(buf, actx.sampleRate)
        if (!r) return
        const midi = midiOf(r.f0)
        onFrame({
          tMs: performance.now() - t0,
          f0: r.f0,
          midi,
          note: noteNameOf(midi),
          cent: centOf(r.f0, midi),
        })
      }, intervalMs)
    } catch {
      // 不支持 Web Audio / 设备异常：实时线降级为不显示（录音与评分不受影响）
      stop()
    }
  }

  function stop() {
    if (timer) clearInterval(timer)
    timer = null
    if (source) {
      try {
        source.disconnect()
      } catch {
        /* 已断开则忽略 */
      }
    }
    source = null
    analyser = null
    buf = null
    if (ctx) {
      try {
        void ctx.close()
      } catch {
        /* 已关闭则忽略 */
      }
    }
    ctx = null
    active = false
  }

  return { start, stop, get active() { return active } }
}
