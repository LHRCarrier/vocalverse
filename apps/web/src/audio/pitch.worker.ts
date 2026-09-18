/**
 * 实时音高检测 Worker（**薄适配器**：只做消息分发与 transfer 回传，不含算法）。
 *
 * 为什么在这里：YIN 单帧约 116 万次乘加（44.1k/48k 窗 2048），跑主线程会周期性阻塞
 * 渲染（跟唱卡顿根因之一，见 local/sing-bench-before-*.json）→ 整体挪到 Worker。
 *
 * 协议（类型定义在 audio/pitch-engine.ts）：
 *   → { type:'init', sampleRate } / { type:'ref', f0s } /
 *     { type:'pcm', pcm, tMs } / { type:'stop' }
 *   ← { type:'frame', frame, score, pcm } | { type:'silent', score, pcm }
 * pcm 以 transfer 送出、原样 transfer 回：主线程 2 个 buffer 循环用，**零分配**。
 *
 * 测试说明：本文件不进单测（happy-dom 无 module Worker）；算法与编排在
 * lib/yin.ts 与 audio/pitch-engine.ts 两个纯模块里覆盖。
 */
import { createPitchEngine, type PitchWorkerIn, type PitchWorkerOut } from '@/audio/pitch-engine'

/**
 * Worker 全局作用域类型：tsconfig.app 的 lib 只含 DOM（无 WebWorker），
 * `/// <reference lib="webworker" />` 会与 DOM 重复声明冲突 → 模块作用域局部声明（遮蔽全局 self）。
 */
declare const self: {
  onmessage: ((ev: MessageEvent<PitchWorkerIn>) => void) | null
  postMessage: (msg: PitchWorkerOut, transfer?: Transferable[]) => void
}

const engine = createPitchEngine()

self.onmessage = (ev) => {
  const m = ev.data
  switch (m.type) {
    case 'init':
      engine.init(m.sampleRate)
      break
    case 'ref':
      engine.setRef(m.f0s)
      break
    case 'pcm': {
      const { frame, score } = engine.tick(m.pcm, m.tMs)
      const out: PitchWorkerOut = frame
        ? { type: 'frame', frame, score, pcm: m.pcm }
        : { type: 'silent', score, pcm: m.pcm }
      self.postMessage(out, [m.pcm.buffer])
      break
    }
    case 'stop':
      break
  }
}