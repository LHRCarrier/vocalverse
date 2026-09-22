/**
 * 录音暂停/继续测试（audio/recorder，2026-09-22 深色录唱页新增能力）。
 *
 * 断言点（都对应真实风险）：
 * - 暂停后 `state==='paused'`、`MediaRecorder.pause()` 被调用、麦克风**不释放**（继续要能续录）；
 * - 暂停段**不计入** `onStop` 上报的时长（评分与「已录」都按有效录音时长）；
 * - 继续后按**剩余额度**重挂自动停止（不是重新数满 3 分钟）；
 * - 暂停中也能「完成」（stop）与「重录」（cancel），不会卡死；
 * - 非录音态的 pause/resume 是幂等空操作。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { VoiceRecorder } from '@/audio/recorder'

class FakeTrack {
  stopped = false
  stop() {
    this.stopped = true
  }
}

class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = []
  state: 'inactive' | 'recording' | 'paused' = 'inactive'
  ondataavailable: ((e: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  pause = vi.fn(() => {
    this.state = 'paused'
  })
  resume = vi.fn(() => {
    this.state = 'recording'
  })
  start = vi.fn(() => {
    this.state = 'recording'
  })
  stop = vi.fn(() => {
    this.state = 'inactive'
    this.onstop?.()
  })
  constructor(
    public stream: unknown,
    public opts: unknown,
  ) {
    FakeMediaRecorder.instances.push(this)
  }
  static isTypeSupported() {
    return true
  }
}

const track = new FakeTrack()

beforeEach(() => {
  vi.useFakeTimers()
  FakeMediaRecorder.instances = []
  vi.stubGlobal('MediaRecorder', FakeMediaRecorder)
  vi.stubGlobal('navigator', {
    mediaDevices: { getUserMedia: vi.fn(async () => ({ getTracks: () => [track] })) },
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('VoiceRecorder · 暂停/继续', () => {
  it('暂停 → paused 态 + MediaRecorder.pause()；麦克风不释放', async () => {
    const r = new VoiceRecorder()
    await r.start(180_000)
    expect(r.state).toBe('recording')
    expect(r.liveStream).not.toBeNull()

    r.pause()
    expect(r.state).toBe('paused')
    expect(FakeMediaRecorder.instances[0].pause).toHaveBeenCalledTimes(1)
    expect(track.stopped).toBe(false) // 继续要能续录：不行释放轨道
  })

  it('继续 → recording 态；按**剩余额度**重挂自动停止（不是重新数满）', async () => {
    const r = new VoiceRecorder()
    await r.start(10_000)
    vi.advanceTimersByTime(4_000) // 已录 4s
    r.pause()
    vi.advanceTimersByTime(30_000) // 暂停 30s：不消耗额度、也不触发自动停止
    expect(r.state).toBe('paused')
    r.resume()
    expect(r.state).toBe('recording')
    vi.advanceTimersByTime(5_900) // 4+5.9 = 9.9s < 10s
    expect(r.state).toBe('recording')
    vi.advanceTimersByTime(200) // 越过剩余额度 → 自动停止
    expect(FakeMediaRecorder.instances[0].stop).toHaveBeenCalled()
  })

  it('暂停段不计入上报时长（onStop 的 durationMs 只算有效录音）', async () => {
    const r = new VoiceRecorder()
    const onStop = vi.fn()
    r.onStop = onStop
    await r.start(180_000)
    vi.advanceTimersByTime(3_000)
    r.pause()
    vi.advanceTimersByTime(20_000)
    r.resume()
    vi.advanceTimersByTime(2_000)
    r.stop()
    const [, , durationMs] = onStop.mock.calls[0]
    expect(durationMs).toBeGreaterThanOrEqual(4_900)
    expect(durationMs).toBeLessThan(5_200) // 3s + 2s（暂停的 20s 不含）
  })

  it('暂停中「完成」（stop）与「重录」（cancel）都可用，不卡死', async () => {
    const a = new VoiceRecorder()
    const onStopA = vi.fn()
    a.onStop = onStopA
    await a.start()
    a.pause()
    a.stop()
    expect(onStopA).toHaveBeenCalledTimes(1)

    const b = new VoiceRecorder()
    const onStopB = vi.fn()
    b.onStop = onStopB
    await b.start()
    b.pause()
    b.cancel()
    expect(onStopB).not.toHaveBeenCalled() // 放弃不上传
    expect(b.state).toBe('idle')
  })

  it('非录音态的 pause/resume 幂等空操作（不抛异常）', async () => {
    const r = new VoiceRecorder()
    expect(() => r.pause()).not.toThrow()
    expect(() => r.resume()).not.toThrow()
    expect(r.state).toBe('idle')
    await r.start()
    r.resume() // 录音中 resume：无操作
    expect(r.state).toBe('recording')
  })
})
