/**
 * 录音组件（docs/06 第 8 章）：
 * - audio/webm;codecs=opus（MediaRecorder.isTypeSupported 回退）
 * - v0 录完整段再上传（非流式分片）；单次 ≤60s、唱歌 ≤180s、≤20MB
 */

export const MAX_RECORD_MS = 60_000
/** 最短有效录音：短于此长度视为误触，调用方应丢弃而非上传（避免手滑吃掉一道题） */
export const MIN_RECORD_MS = 800
export const MAX_BYTES = 20 * 1024 * 1024

export type RecorderState = 'idle' | 'recording' | 'stopped' | 'error'

export class RecorderError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'RecorderError'
  }
}

/**
 * 把 getUserMedia 的 DOMException 名译成中文提示。
 * 直接把 `(e as Error).message` 甩到界面上会出现「Permission denied」这类英文原文。
 */
export function micErrorMessage(e: unknown): string {
  const err = e as { name?: string; message?: string } | null
  switch (err?.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return '麦克风权限被拒绝：请在浏览器地址栏的权限设置里允许麦克风后重试'
    case 'NotFoundError':
    case 'OverconstrainedError':
      return '未检测到可用麦克风：请插入或启用录音设备后重试'
    case 'NotReadableError':
      return '麦克风被其他程序占用：请关闭占用它的应用后重试'
    case 'AbortError':
      return '录音设备启动失败，请重试'
    default:
      return err?.message || '录音启动失败，请重试'
  }
}

function pickMimeType(): string {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
  for (const mime of candidates) {
    if (MediaRecorder.isTypeSupported(mime)) return mime
  }
  throw new RecorderError('当前浏览器不支持录音（MediaRecorder）')
}

export class VoiceRecorder {
  private recorder: MediaRecorder | null = null
  private chunks: Blob[] = []
  private timer: ReturnType<typeof setTimeout> | null = null
  /** 启动世代号：cancel() 递增以作废「尚未完成的 start()」（权限提示期间点停止） */
  private startGen = 0
  /** 本次录音已被放弃：onstop 据此跳过 onStop（不上传、不推进题目） */
  private cancelled = false

  state: RecorderState = 'idle'
  onStateChange: ((state: RecorderState) => void) | null = null
  onStop: ((blob: Blob, mime: string, durationMs: number) => void) | null = null

  get supported(): boolean {
    return typeof MediaRecorder !== 'undefined'
  }

  async start(maxMs: number = MAX_RECORD_MS): Promise<void> {
    if (!this.supported) throw new RecorderError('当前浏览器不支持录音')
    if (this.state === 'recording') return

    const gen = ++this.startGen
    this.cancelled = false
    let stream: MediaStream | null = null
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })

      // 权限提示期间调用方按了停止：释放麦克风，不进入 recording，也不产生任何回合。
      if (gen !== this.startGen) {
        stream.getTracks().forEach((t) => t.stop())
        this.setState('idle')
        return
      }

      const mime = pickMimeType()
      const activeStream = stream
      this.chunks = []
      this.recorder = new MediaRecorder(activeStream, { mimeType: mime })

      this.recorder.ondataavailable = (e: BlobEvent) => {
        if (e.data.size > 0) this.chunks.push(e.data)
      }
      this.recorder.onstop = () => {
        const blob = new Blob(this.chunks, { type: mime })
        const durationMs = this.recordedMs
        activeStream.getTracks().forEach((t) => t.stop())
        if (this.cancelled) {
          // 放弃的录音：回到 idle，不触发 onStop（调用方不会上传）
          this.cancelled = false
          this.setState('idle')
          return
        }
        this.setState('stopped')
        this.onStop?.(blob, mime, durationMs)
      }

      this.recordedMs = 0
      this.recordStart = Date.now()
      this.recorder.start()
      this.setState('recording')

      // 自动停止：按场景传入（对话 15s / 唱歌 180s / 默认 60s——docs/14 §3.2）
      this.timer = setTimeout(() => this.stop(), maxMs)
    } catch (e) {
      // 权限被拒 / 无麦克风 / 无可用 mime：释放已拿到的轨道并进入 error 态。
      // 必须发出状态变更，否则「乐观置位」的调用方永远等不到复位信号 → 按钮卡死。
      stream?.getTracks().forEach((t) => t.stop())
      this.recorder = null
      this.setState('error')
      throw e
    }
  }

  /** 正常停止：产出音频并经 onStop 交给调用方。重复调用安全（幂等）。 */
  stop(): void {
    // 守 MediaRecorder 自身的 state：this.state 要等 onstop 这个宏任务才翻成 'stopped'，
    // 期间连点两下会对已 inactive 的 recorder 再 stop() 一次 → InvalidStateError。
    if (this.state !== 'recording') return
    if (!this.recorder || this.recorder.state !== 'recording') return
    this.recordedMs = Date.now() - this.recordStart
    if (this.timer) {
      clearTimeout(this.timer)
      this.timer = null
    }
    this.recorder.stop()
  }

  /**
   * 放弃本次录音：停采集、放麦克风，但**不触发 onStop**（不上传、不推进题目）。
   * 若 start() 仍卡在权限提示上，则作废该次启动，使其完成后直接释放而不进入 recording。
   */
  cancel(): void {
    this.startGen += 1 // 作废尚未完成的 start()
    if (this.recorder && this.state === 'recording' && this.recorder.state === 'recording') {
      this.cancelled = true
      if (this.timer) {
        clearTimeout(this.timer)
        this.timer = null
      }
      this.recorder.stop()
      return
    }
    // 启动窗口内被取消：立刻给调用方一个复位信号，别让按钮悬在录音态。
    this.setState('idle')
  }

  private recordStart = 0
  private recordedMs = 0

  private setState(state: RecorderState): void {
    this.state = state
    this.onStateChange?.(state)
  }
}
