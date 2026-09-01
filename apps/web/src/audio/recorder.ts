/**
 * 录音组件（docs/06 第 8 章）：
 * - audio/webm;codecs=opus（MediaRecorder.isTypeSupported 回退）
 * - v0 录完整段再上传（非流式分片）；单次 ≤60s、唱歌 ≤180s、≤20MB
 */

export const MAX_RECORD_MS = 60_000
export const MAX_BYTES = 20 * 1024 * 1024

export type RecorderState = 'idle' | 'recording' | 'stopped' | 'error'

export class RecorderError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'RecorderError'
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

  state: RecorderState = 'idle'
  onStateChange: ((state: RecorderState) => void) | null = null
  onStop: ((blob: Blob, mime: string, durationMs: number) => void) | null = null

  get supported(): boolean {
    return typeof MediaRecorder !== 'undefined'
  }

  async start(maxMs: number = MAX_RECORD_MS): Promise<void> {
    if (!this.supported) throw new RecorderError('当前浏览器不支持录音')
    if (this.state === 'recording') return

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mime = pickMimeType()
    this.chunks = []
    this.recorder = new MediaRecorder(stream, { mimeType: mime })

    this.recorder.ondataavailable = (e: BlobEvent) => {
      if (e.data.size > 0) this.chunks.push(e.data)
    }
    this.recorder.onstop = () => {
      const blob = new Blob(this.chunks, { type: mime })
      const durationMs = this.recordedMs
      stream.getTracks().forEach((t) => t.stop())
      this.setState('stopped')
      this.onStop?.(blob, mime, durationMs)
    }

    this.recordedMs = 0
    this.recordStart = Date.now()
    this.recorder.start()
    this.setState('recording')

    // 自动停止：按场景传入（对话 15s / 唱歌 180s / 默认 60s——docs/14 §3.2）
    this.timer = setTimeout(() => this.stop(), maxMs)
  }

  stop(): void {
    if (this.recorder && this.state === 'recording') {
      this.recordedMs = Date.now() - this.recordStart
      if (this.timer) clearTimeout(this.timer)
      this.recorder.stop()
    }
  }

  private recordStart = 0
  private recordedMs = 0

  private setState(state: RecorderState): void {
    this.state = state
    this.onStateChange?.(state)
  }
}
