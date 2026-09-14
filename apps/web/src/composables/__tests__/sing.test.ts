/**
 * 唱吧组合式状态机测试（M3 唱歌 P0）：
 * - useSingPlay 状态机：openSong 门禁（40905 → false + error）、
 *   submitAudio → processing → （假时钟轮询后）done + result、轮询 failed、reset；
 * - 录音状态机（放弃重录复位 / 关闭面板取消录音）、轮询世代号（P1-2）、收藏切换。
 *
 * 2026-09-10 拆分（eslint `max-lines 350`，新代码不豁免）：
 * - 纯映射函数用例 → `api/__tests__/sing-messages.test.ts`（API 层）；
 * - 共享脚手架（录音器伪实现 + API 替换 + 夹具）→ `./singTestUtils.ts`。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'

import { detail, installMock, rec } from './singTestUtils'

describe('useSingPlay 录音状态机（2026-09-10「放弃重录」卡死 BUG 回归）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.doUnmock('@/api/sing')
    vi.doUnmock('@/audio/recorder')
  })

  it('放弃重录：recorder 发 idle → phase 必须复位（修复前停在 recording，整页按钮失效）', async () => {
    const { useSingPlay } = await installMock()
    const play = useSingPlay()

    play.startRecording()
    await vi.advanceTimersByTimeAsync(0)
    expect(play.phase.value).toBe('recording')
    expect(play.getLiveStream()).not.toBeNull()

    play.cancelRecording() // 「放弃重录」
    await vi.advanceTimersByTimeAsync(0)
    expect(play.phase.value).toBe('idle') // ← 修复前为 'recording'（主按钮永久禁用 + 停止条空操作）
    expect(play.getLiveStream()).toBeNull()
    expect(rec.instance?.state).toBe('idle')
  })

  it('放弃后可以重新开始录音（不残留录音态）', async () => {
    const { useSingPlay } = await installMock()
    const play = useSingPlay()
    play.startRecording()
    await vi.advanceTimersByTimeAsync(0)
    play.cancelRecording()
    await vi.advanceTimersByTimeAsync(0)

    play.startRecording() // 再点「开始跟唱」
    await vi.advanceTimersByTimeAsync(0)
    expect(play.phase.value).toBe('recording')
  })

  it('正常停止不受复位影响：stopped → 立刻 uploading（不闪回 idle、不重复上传）', async () => {
    const create = vi.fn(async () => ({ id: 5, kind: 'sing', song_id: 1, assigned_turns: 2 }))
    const { useSingPlay } = await installMock({ createSingSession: create })
    const play = useSingPlay()
    await play.loadSongs()
    await play.openSong(1)
    play.startRecording()
    await vi.advanceTimersByTimeAsync(0)

    play.stopRecording() // onStateChange('stopped') → onStop → submitAudio
    expect(play.phase.value).toBe('uploading')
    await vi.advanceTimersByTimeAsync(0)
    expect(create).toHaveBeenCalledTimes(1)
  })

  it('录音启动失败（error 态）仍进 failed（保留原语义）', async () => {
    const { useSingPlay } = await installMock()
    const play = useSingPlay()
    play.startRecording()
    await vi.advanceTimersByTimeAsync(0)
    rec.instance?.onStateChange?.('error')
    expect(play.phase.value).toBe('failed')
  })

  it('关闭面板（reset）必须取消在录的录音；之后能正常重新开始（修复前必失败）', async () => {
    const { useSingPlay } = await installMock()
    const play = useSingPlay()
    play.startRecording()
    await vi.advanceTimersByTimeAsync(0)
    expect(play.phase.value).toBe('recording')

    play.reset() // 面板顶部 chevron 关闭 → startOver() → reset()
    await vi.advanceTimersByTimeAsync(0)
    expect(rec.instance?.state).toBe('idle') // 修复前仍是 'recording'（录音被遗弃、麦克风未释放）
    expect(play.getLiveStream()).toBeNull()

    await play.loadSongs()
    await play.openSong(1)
    play.startRecording() // 修复前：start() 同态守卫静默早退 → phase 停在 idle，界面毫无反应
    await vi.advanceTimersByTimeAsync(0)
    expect(play.phase.value).toBe('recording')
  })

  it('retry() 同样收尾在录的录音（错误态复位不留活录音）', async () => {
    const { useSingPlay } = await installMock()
    const play = useSingPlay()
    play.startRecording()
    await vi.advanceTimersByTimeAsync(0)

    play.retry()
    expect(rec.instance?.state).toBe('idle')
    expect(play.phase.value).toBe('idle')
  })

  it('P1-2：重置后**在飞**轮询落地不得写状态（换歌串台的根因）', async () => {
    // 用 holder 对象持有 resolve（直接 `let x: fn | null` 会被 TS 收窄成 never，调用报 TS2349）
    const pending: { land?: (v: unknown) => void } = {}
    const { useSingPlay } = await installMock({
      fetchSingStatus: vi.fn(
        () =>
          new Promise((resolve) => {
            pending.land = resolve
          }),
      ),
    })
    const play = useSingPlay()
    await play.loadSongs()
    await play.openSong(1)
    const p = play.submitAudio(new Blob(['x']))
    await vi.advanceTimersByTimeAsync(0)
    await p
    expect(play.phase.value).toBe('processing')

    await vi.advanceTimersByTimeAsync(1600) // 首轮 status 已发出并挂起
    play.reset() // 关面板/换歌 → 世代失效
    pending.land?.({ attempt_id: 9, status: 'done', progress: { done_lines: 2, total: 2 } })
    await vi.advanceTimersByTimeAsync(50)

    expect(play.result.value).toBeNull() // 修复前：迟到结果把 result 写回来
    expect(play.phase.value).toBe('idle')
  })

  it('P1-2：reset 会 abort 在飞请求（不只清定时器）', async () => {
    const signals: (AbortSignal | undefined)[] = []
    const { useSingPlay } = await installMock({
      fetchSingStatus: vi.fn((_id: number, signal?: AbortSignal) => {
        signals.push(signal)
        return new Promise(() => {})
      }),
    })
    const play = useSingPlay()
    await play.loadSongs()
    await play.openSong(1)
    const p = play.submitAudio(new Blob(['x']))
    await vi.advanceTimersByTimeAsync(0)
    await p
    await vi.advanceTimersByTimeAsync(1600)

    expect(signals.length).toBe(1)
    expect(signals[0]?.aborted).toBe(false)
    play.reset()
    expect(signals[0]?.aborted).toBe(true) // 修复前：无 AbortController，请求继续跑
  })

  it('P1-2：openSong 换歌会作废旧轮询并取消在录录音', async () => {
    const { useSingPlay } = await installMock()
    const play = useSingPlay()
    await play.loadSongs()
    await play.openSong(1)
    play.startRecording()
    await vi.advanceTimersByTimeAsync(0)
    expect(play.phase.value).toBe('recording')

    await play.openSong(1) // 换歌（同 id 也走同一条清理路径）
    expect(rec.instance?.state).toBe('idle') // 录音被取消（修复前仍在录）
    expect(play.phase.value).toBe('idle')
  })
})
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

describe('useSingPlay 收藏（2026-09-10）', () => {
  afterEach(() => {
    vi.doUnmock('@/api/sing')
  })

  it('toggleFavorite：收藏 → favorited=true 且 favorites 收录；再点 → 取消', async () => {
    const fav = vi.fn(async (songId: number, favorited: boolean) => ({ song_id: songId, favorited }))
    const { useSingPlay } = await installMock({ setSongFavorite: fav })
    const play = useSingPlay()
    await play.loadSongs()
    expect(play.favorites.value).toHaveLength(0)

    expect(await play.toggleFavorite(1)).toBe(true)
    expect(fav).toHaveBeenCalledWith(1, true)
    expect(play.songs.value[0].favorited).toBe(true)
    expect(play.favorites.value.map((s) => s.id)).toEqual([1])

    expect(await play.toggleFavorite(1)).toBe(false)
    expect(fav).toHaveBeenLastCalledWith(1, false)
    expect(play.songs.value[0].favorited).toBe(false)
    expect(play.favorites.value).toHaveLength(0)
  })

  it('toggleFavorite：详情已加载时同步 detail.favorited', async () => {
    const { useSingPlay } = await installMock()
    const play = useSingPlay()
    await play.loadSongs()
    await play.openSong(1)
    await play.toggleFavorite(1)
    expect(play.detail.value?.favorited).toBe(true)
  })

  it('toggleFavorite：请求失败 → 回滚为原状态并返回 null（不静默、不留假状态）', async () => {
    const { useSingPlay } = await installMock({
      setSongFavorite: vi.fn(async () => {
        throw new Error('boom')
      }),
    })
    const play = useSingPlay()
    await play.loadSongs()
    expect(await play.toggleFavorite(1)).toBeNull()
    expect(play.songs.value[0].favorited).toBe(false)
    expect(play.favorites.value).toHaveLength(0)
    expect(play.favoriteError.value).toBe('收藏操作失败，请重试')
  })

  // 404/401/5xx 的「可诊断文案」由 favoriteErrorMessage 的纯函数用例 + MobileSingView 集成用例覆盖
  // （此处不重复：本文件的 doMock 模块图与真实映射函数的 ApiError 不是同一个类实例，instanceof 会回落通用文案）

  it('toggleFavorite：未知歌曲 id → null（不发请求）', async () => {
    const fav = vi.fn()
    const { useSingPlay } = await installMock({ setSongFavorite: fav })
    const play = useSingPlay()
    await play.loadSongs()
    expect(await play.toggleFavorite(999)).toBeNull()
    expect(fav).not.toHaveBeenCalled()
  })
})

void ApiError
