/**
 * 实时音高检测器（docs/06 §9.4 注记：练习辅助，评分以离线 pyin 为准）。
 *
 * 链路：同一 MediaStream（recorder.liveStream，不二次申请麦克风）→
 * AudioContext → AnalyserNode(fftSize 2048, 无平滑) → getFloatTimeDomainData →
 * **transfer 给 Worker**（audio/pitch.worker + audio/pitch-engine + lib/yin）→ onFrame。
 *
 * 2026-09-18 性能改造（跟唱卡顿根因：YIN 单帧 ≈116 万次乘加 + 每次 2 个 Float64Array 分配，
 * 全压在主线程；基线见 local/sing-bench-before-*.json）：重 DSP 全部移入 Worker；
 * 主线程只保留 2 个 Float32Array 的池（AnalyserNode 是 DOM API，不能进 Worker）——
 * tick 取池 → 拷窗 → transfer 送出，Worker 回执把同一 buffer 送回池，**常规路径零分配**。
 * Worker 落后时池空即丢本 tick（实时线允许丢帧，不排队堆积；录音/离线评分不受影响）。
 *
 * 约定：
 * - 帧率 ~60ms（≈16fps 更新 + canvas rAF 独立渲染）；窗 2048@44.1/48k ≈ 42~46ms；
 * - start() 幂等（先停旧的）；stop() 断开并 close AudioContext + terminate Worker（防泄漏）；
 * - YIN null（静音/噪声）不回调——但**每个 tick 都有回执**（frame/silent），
 *   绘制侧用 `lastTickAt` 区分「没出声」（视口照走）与「检测停摆」（冻结 + 淡出）；
 * - 时间戳 = start 后经过 ms（参考线 t0=录音开始，练习辅助口径，不做整首对齐）。
 */

import type { PitchWorkerOut } from '@/audio/pitch-engine'
import type { LiveScoreRead } from '@/lib/live-score'
import { YIN_WINDOW_SIZE } from '@/lib/yin'

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
  /**
   * `opts.refF0s` = 参考旋律（按 32ms 槽压平，live-chart.flattenRefF0s）——
   * 传入后 Worker 每 tick 与之比对，经 `onScore` 回传滚动实时分（练习参考口径）。
   */
  start: (stream: MediaStream, opts?: { refF0s?: Float32Array | null }) => void
  stop: () => void
  readonly active: boolean
  /**
   * 本次检测起点的 `performance.now()` 基准（未运行/已停止 → null）。
   * 帧时间戳 = performance.now() - startedAt；绘制视口用它做**时间基平滑推进**
   * （2026-09-18：旧实现按「最后一帧 tMs」跳变，数据 16.7fps → 画面每 60ms 跳一次）。
   */
  readonly startedAt: number | null
  /**
   * 最近一次 Worker 回执的 `performance.now()`（检测链路活性；未运行 → null）。
   * 与「最近一帧」不同：静音/噪声导致 YIN 返回 null 时**不产生帧但有回执**，
   * 绘制侧据此区分「用户没出声」与「Worker/检测停摆」。
   */
  readonly lastTickAt: number | null
}

/** PCM 池大小：2 个窗足够（Worker 单帧 <60ms）；池空 = Worker 落后 → 丢本 tick */
const POOL_SIZE = 2

export function createLivePitch(
  onFrame: (frame: LivePitchFrame) => void,
  intervalMs: number = 60,
  onScore?: (score: LiveScoreRead) => void,
): LivePitchHandles {
  let ctx: AudioContext | null = null
  let source: MediaStreamAudioSourceNode | null = null
  let analyser: AnalyserNode | null = null
  let timer: ReturnType<typeof setInterval> | null = null
  let worker: Worker | null = null
  let pool: Float32Array[] = []
  let t0 = 0
  let lastTick = 0
  let active = false

  function start(stream: MediaStream, opts?: { refF0s?: Float32Array | null }) {
    stop()
    try {
      const Ctor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      ctx = new Ctor()
      source = ctx.createMediaStreamSource(stream)
      analyser = ctx.createAnalyser()
      // 窗长 = YIN_WINDOW_SIZE（4096@48k ≈ 85ms）：更长窗 = 更多积分 = 弱信号检出率更高
      // （2026-09-21 实测，见 lib/yin.ts 注释）。必须与 Worker 侧 detector 的窗长一致。
      analyser.fftSize = YIN_WINDOW_SIZE
      analyser.smoothingTimeConstant = 0
      source.connect(analyser)
      // Vite 要求 new URL 参数为字面量（勿拼接/勿用别名）
      const w = new Worker(new URL('../audio/pitch.worker.ts', import.meta.url), { type: 'module' })
      worker = w
      w.onmessage = (ev: MessageEvent<PitchWorkerOut>) => {
        const m = ev.data
        lastTick = performance.now()
        if (pool.length < POOL_SIZE) pool.push(m.pcm) // 原样回池：下一次 tick 复用同一 buffer
        if (m.type === 'frame') onFrame(m.frame)
        if (m.score && onScore) onScore(m.score) // 节流 ≤4Hz（引擎侧控制）
      }
      w.postMessage({ type: 'init', sampleRate: ctx.sampleRate })
      w.postMessage({ type: 'ref', f0s: opts?.refF0s ?? null })
      pool = [new Float32Array(analyser.fftSize), new Float32Array(analyser.fftSize)]
      t0 = performance.now()
      lastTick = t0
      // 用户手势链内创建；resume 失败仅掉实时线，不阻塞录音（practice 辅助语义）
      void ctx.resume().catch(() => {})
      active = true
      const actx = ctx
      timer = setInterval(() => {
        const buf = pool.pop()
        if (!analyser || !buf || !actx) return
        analyser.getFloatTimeDomainData(buf)
        w.postMessage({ type: 'pcm', pcm: buf, tMs: performance.now() - t0 }, [buf.buffer])
      }, intervalMs)
    } catch {
      // 不支持 Web Audio / Worker：实时线降级为不显示（录音与评分不受影响）
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
    pool = []
    if (worker) worker.terminate()
    worker = null
    if (ctx) {
      try {
        void ctx.close()
      } catch {
        /* 已关闭则忽略 */
      }
    }
    ctx = null
    active = false
    lastTick = 0
  }

  return {
    start,
    stop,
    get active() {
      return active
    },
    get startedAt() {
      return active ? t0 : null
    },
    get lastTickAt() {
      return active ? lastTick : null
    },
  }
}