import { beforeEach, describe, expect, it, vi } from 'vitest'

import { micErrorMessage, MIN_RECORD_MS, VoiceRecorder } from '../recorder'

/** 忠实于规范的 MediaRecorder 假件：对 inactive 的实例再 stop() 必须抛 InvalidStateError。 */
class FakeMediaRecorder {
  static isTypeSupported = () => true
  state: 'inactive' | 'recording' = 'inactive'
  ondataavailable: ((e: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null

  start(): void {
    this.state = 'recording'
  }

  stop(): void {
    if (this.state === 'inactive') {
      throw Object.assign(new Error("MediaRecorder's state is 'inactive'"), {
        name: 'InvalidStateError',
      })
    }
    this.state = 'inactive'
    // 真实实现里 onstop 是下一个任务才派发，正是「连点两下」的竞态窗口
    setTimeout(() => {
      this.ondataavailable?.({ data: new Blob(['audio']) })
      this.onstop?.()
    }, 0)
  }
}

const tick = () => new Promise((r) => setTimeout(r, 0))

function defer<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function makeStream() {
  const track = { stop: vi.fn() }
  return { track, stream: { getTracks: () => [track] } as unknown as MediaStream }
}

let getUserMedia: ReturnType<typeof vi.fn>

beforeEach(() => {
  ;(globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder = FakeMediaRecorder
  getUserMedia = vi.fn()
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  })
})

/** 装配一个录音机 + 记录状态流与上传回调，模拟 PlacementView 的接线方式 */
function wire() {
  const rec = new VoiceRecorder()
  const states: string[] = []
  const uploads: number[] = []
  // 与三个 View 一致：非 recording 即复位按钮
  let recording = false
  rec.onStateChange = (s) => {
    states.push(s)
    if (s !== 'recording') recording = false
  }
  rec.onStop = (_blob, _mime, durationMs) => uploads.push(durationMs)
  return {
    rec,
    states,
    uploads,
    get recording() {
      return recording
    },
    set recording(v: boolean) {
      recording = v
    },
  }
}

describe('VoiceRecorder 停止/取消语义', () => {
  it('正常录音后 stop() → 走 onStop 上传，按钮复位', async () => {
    const { stream } = makeStream()
    getUserMedia.mockResolvedValue(stream)
    const v = wire()
    v.recording = true

    await v.rec.start(15_000)
    expect(v.rec.state).toBe('recording')
    v.rec.stop()
    await tick()

    expect(v.uploads).toHaveLength(1)
    expect(v.rec.state).toBe('stopped')
    expect(v.recording).toBe(false)
  })

  it('连点两下停止键不抛 InvalidStateError，且只上传一次', async () => {
    const { stream } = makeStream()
    getUserMedia.mockResolvedValue(stream)
    const v = wire()
    await v.rec.start(15_000)

    v.rec.stop()
    // onstop 尚未派发，this.state 仍是 'recording' —— 修复前这一下会抛
    expect(() => v.rec.stop()).not.toThrow()
    await tick()

    expect(v.uploads).toHaveLength(1)
  })

  it('权限提示期间 cancel() 后用户点「允许」→ 不录音、不上传、释放麦克风', async () => {
    const { track, stream } = makeStream()
    const d = defer<MediaStream>()
    getUserMedia.mockReturnValue(d.promise)
    const v = wire()
    v.recording = true

    const p = v.rec.start(15_000)
    v.rec.cancel() // 用户在权限气泡还开着时按了 ■
    expect(v.recording).toBe(false) // 按钮立刻复位，不等权限结果

    d.resolve(stream)
    await p
    await tick()

    expect(v.rec.state).toBe('idle')
    expect(v.uploads).toHaveLength(0) // 关键：不能上传空录音吃掉一道题
    expect(track.stop).toHaveBeenCalled() // 关键：麦克风必须释放
  })

  it('权限提示期间 cancel() 后用户点「拒绝」→ 进入 error 态并复位，按钮不卡死', async () => {
    const d = defer<MediaStream>()
    getUserMedia.mockReturnValue(d.promise)
    const v = wire()
    v.recording = true

    const p = v.rec.start(15_000)
    v.rec.cancel()
    d.reject(Object.assign(new Error('Permission denied'), { name: 'NotAllowedError' }))

    await expect(p).rejects.toThrow()
    expect(v.recording).toBe(false) // 修复前这里会永久停在 true
    expect(v.states).toContain('error')
  })

  it('start() 失败必须发出 error 状态（Practice/Defense 靠它复位按钮）', async () => {
    getUserMedia.mockRejectedValue(
      Object.assign(new Error('Requested device not found'), { name: 'NotFoundError' }),
    )
    const v = wire()
    v.recording = true

    await expect(v.rec.start(15_000)).rejects.toThrow()
    expect(v.states).toEqual(['error'])
    expect(v.recording).toBe(false)
  })

  it('录音中 cancel() → 停采集、放麦克风，但不触发 onStop', async () => {
    const { track, stream } = makeStream()
    getUserMedia.mockResolvedValue(stream)
    const v = wire()
    await v.rec.start(15_000)

    v.rec.cancel()
    await tick()

    expect(v.uploads).toHaveLength(0)
    expect(v.rec.state).toBe('idle')
    expect(track.stop).toHaveBeenCalled()
  })

  it('cancel() 后仍可重新开始录音', async () => {
    const { stream } = makeStream()
    getUserMedia.mockResolvedValue(stream)
    const v = wire()

    await v.rec.start(15_000)
    v.rec.cancel()
    await tick()

    await v.rec.start(15_000)
    expect(v.rec.state).toBe('recording')
    v.rec.stop()
    await tick()
    expect(v.uploads).toHaveLength(1)
  })

  it('stop() 报出的时长可用于最短录音判定', async () => {
    const { stream } = makeStream()
    getUserMedia.mockResolvedValue(stream)
    const v = wire()

    await v.rec.start(15_000)
    v.rec.stop() // 立刻停 → 时长远小于 MIN_RECORD_MS
    await tick()

    expect(v.uploads[0]).toBeLessThan(MIN_RECORD_MS)
  })
})

describe('micErrorMessage', () => {
  it('把 getUserMedia 的 DOMException 译成中文而非英文原文', () => {
    expect(micErrorMessage({ name: 'NotAllowedError', message: 'Permission denied' })).toContain(
      '权限被拒绝',
    )
    expect(micErrorMessage({ name: 'NotFoundError' })).toContain('未检测到可用麦克风')
    expect(micErrorMessage({ name: 'NotReadableError' })).toContain('被其他程序占用')
  })

  it('未知错误回退到原始 message，再兜底到通用文案', () => {
    expect(micErrorMessage({ name: 'WeirdError', message: 'boom' })).toBe('boom')
    expect(micErrorMessage(null)).toBe('录音启动失败，请重试')
  })
})
