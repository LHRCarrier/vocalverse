/**
 * 唱吧 API/组合式状态机测试（M3 唱歌 P0）：
 * - singErrorMessage 错误码文案映射（40905/41302/40002/42901）；
 * - useSingPlay 状态机：openSong 门禁（40905 → false + error）、
 *   submitAudio → processing → （假时钟轮询后）done + result、轮询 failed、reset。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { singErrorMessage } from '@/api/sing'
import type { SingAttemptResult, SongDetail } from '@/api/sing'

describe('singErrorMessage（docs/api/error-codes.md 文案映射）', () => {
  it('40905 参考旋律未就绪', () => {
    expect(singErrorMessage(new ApiError(40905, 'x', 409))).toContain('参考旋律')
  })
  it('41302 时长超限', () => {
    expect(singErrorMessage(new ApiError(41302, 'x', 413))).toContain('3 分钟')
  })
  it('40002 音频过短', () => {
    expect(singErrorMessage(new ApiError(40002, 'x', 400))).toContain('重录')
  })
  it('42901 限流提示', () => {
    expect(singErrorMessage(new ApiError(42901, 'x', 429))).toContain('5 次')
  })
  it('未知错误回退 message', () => {
    expect(singErrorMessage(new ApiError(50001, '上游超时', 500))).toBe('上游超时')
  })
})

const detail = (status: string): SongDetail => ({
  id: 1,
  title: 'Twinkle',
  level: 1,
  pitch_ref_status: status as SongDetail['pitch_ref_status'],
  expected_lines: 2,
  lines: [],
})

const fullResult: SingAttemptResult = {
  id: 9,
  song_id: 1,
  duration_s: 10,
  overall: 91.1,
  pitch: 95,
  rhythm: 95,
  pron: 82,
  is_complete: true,
  expected_lines: 2,
  scoring_version: 'v1',
  ref_version: 'pyin-v1',
  lines: [],
  alignment: { offset_ms: 0, method: 'dtw-sakoe-chiba-v1' },
}

interface ApiMock {
  fetchSongDetail?: ReturnType<typeof vi.fn>
  fetchSongs?: ReturnType<typeof vi.fn>
  createSingSession?: ReturnType<typeof vi.fn>
  uploadSingAudio?: ReturnType<typeof vi.fn>
  fetchSingStatus?: ReturnType<typeof vi.fn>
  fetchSingResult?: ReturnType<typeof vi.fn>
}

async function installMock(overrides: ApiMock = {}) {
  vi.resetModules()
  const { ApiError: ClientApiError } = await import('@/api/client')
  vi.doMock('@/api/sing', () => ({
    fetchSongDetail: overrides.fetchSongDetail ?? vi.fn(async () => detail('ready')),
    fetchSongs: overrides.fetchSongs ?? vi.fn(async () => [
      { id: 1, title: 'T', level: 1, pitch_ref_status: 'ready', expected_lines: 2 },
    ]),
    createSingSession: overrides.createSingSession ?? vi.fn(async () => ({ id: 5, kind: 'sing', song_id: 1, assigned_turns: 2 })),
    uploadSingAudio: overrides.uploadSingAudio ?? vi.fn(async () => ({
      attempt_id: 9,
      status: 'queued',
      progress: { done_lines: 0, total: 2 },
    })),
    fetchSingStatus: overrides.fetchSingStatus ?? vi.fn(async () => ({
      attempt_id: 9,
      status: 'done',
      progress: { done_lines: 2, total: 2 },
    })),
    fetchSingResult: overrides.fetchSingResult ?? vi.fn(async () => fullResult),
    ApiError: ClientApiError,
  }))
  const { useSingPlay } = await import('@/composables/sing')
  return { useSingPlay }
}

describe('useSingPlay 状态机', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.doUnmock('@/api/sing')
  })

  it('openSong 就绪门禁：未就绪 → false + 错误文案', async () => {
    const { useSingPlay } = await installMock({
      fetchSongDetail: vi.fn(async () => detail('missing')),
    })
    const play = useSingPlay()
    const ok = await play.openSong(1)
    expect(ok).toBe(false)
    expect(play.error.value).toContain('参考旋律')
  })

  it('openSong 就绪 → 进入 idle', async () => {
    const { useSingPlay } = await installMock()
    const play = useSingPlay()
    const ok = await play.openSong(1)
    expect(ok).toBe(true)
    expect(play.phase.value).toBe('idle')
    expect(play.detail.value?.expected_lines).toBe(2)
  })

  it('submitAudio → uploading → processing →（轮询后）done + result', async () => {
    const { useSingPlay } = await installMock()
    const play = useSingPlay()
    await play.openSong(1)

    const p = play.submitAudio(new Blob(['x'], { type: 'audio/webm' }))
    expect(play.phase.value).toBe('uploading')
    await vi.advanceTimersByTimeAsync(0) // 上传微任务落地
    await p
    expect(play.status.value?.attempt_id).toBe(9)
    expect(play.phase.value).toBe('processing')

    await vi.advanceTimersByTimeAsync(1600) // 首次轮询（1500ms 间隔）
    expect(play.phase.value).toBe('done')
    expect(play.result.value?.overall).toBe(91.1)
  })

  it('轮询 failed → phase failed + 错误文案', async () => {
    const { useSingPlay } = await installMock({
      fetchSingStatus: vi.fn(async () => ({
        attempt_id: 9,
        status: 'failed',
        progress: { done_lines: 0, total: 2 },
        error: 'pipeline crash',
      })),
    })
    const play = useSingPlay()
    await play.openSong(1)
    const p = play.submitAudio(new Blob(['x']))
    await vi.advanceTimersByTimeAsync(0)
    await p
    await vi.advanceTimersByTimeAsync(1600)
    expect(play.phase.value).toBe('failed')
    expect(play.error.value).toContain('pipeline crash')
  })

  it('reset 清空状态回到 idle', async () => {
    const { useSingPlay } = await installMock()
    const play = useSingPlay()
    await play.openSong(1)
    play.reset()
    expect(play.detail.value).toBeNull()
    expect(play.result.value).toBeNull()
    expect(play.phase.value).toBe('idle')
  })
})

void ApiError
