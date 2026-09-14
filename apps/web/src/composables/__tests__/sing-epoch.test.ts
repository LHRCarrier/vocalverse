/**
 * `useSingPlay` 世代号不变量 + 换歌清态（2026-09-14 · PR #34 评审 R3/R4 回归）。
 *
 * 抽成独立文件的原因：`sing.test.ts` 已逼近 eslint `max-lines 350` 门禁（新代码不豁免），
 * 共享脚手架复用 `./singTestUtils`。
 *
 * 两条被审出的洞（都不是"测试全绿"能覆盖的）：
 * - **R3**：`openSong()` 只清 `detail`/`error`，`reset()` 里清的 `status`/`result`/`phase`
 *   没清 → **报告态直接换歌**时旧报告仍挂在状态里；
 * - **R4**：`submitAudio` 自增一次、`poll()` 又自增一次 → `reset()`/`openSong()` 若发生在
 *   `createSingSession` / `uploadSingAudio` 的 await 期间，它那次 bump 会被 `poll()` 的 bump
 *   **覆盖**（`my === epoch` 重新成立）→ 迟到结果照写，注释声称的"换歌/重置即作废"并不成立。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { installMock } from './singTestUtils'

describe('useSingPlay 世代号不变量（评审 R4：poll 不得覆盖 reset/openSong 的 bump）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.doUnmock('@/api/sing')
    vi.doUnmock('@/audio/recorder')
  })

  it('reset() 落在上传 await 期间：迟到回执不落地（修复前 phase 被改成 processing 并继续轮询）', async () => {
    // holder 对象持有 resolve（`let x: fn | null` 会被 TS 收窄成 never，调用报 TS2349）
    const pending: { land?: (v: unknown) => void } = {}
    const { useSingPlay } = await installMock({
      uploadSingAudio: vi.fn(
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
    await vi.advanceTimersByTimeAsync(0) // createSingSession 落地，卡在 upload
    expect(play.phase.value).toBe('uploading')

    play.reset() // 关面板 / 再来一遍
    pending.land?.({ attempt_id: 9, status: 'queued', progress: { done_lines: 0, total: 2 } })
    await vi.advanceTimersByTimeAsync(0)
    await p

    expect(play.status.value).toBeNull() // 修复前：迟到回执写回 status 并起轮询（跑旧 attempt）
    expect(play.phase.value).toBe('idle') // 修复前：被改成 processing（随后还会自己走到 done）
  })

  it('openSong() 换歌落在上传 await 期间：旧歌回执不写到新歌上', async () => {
    const pending: { land?: (v: unknown) => void } = {}
    const { useSingPlay } = await installMock({
      uploadSingAudio: vi.fn(
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
    await play.openSong(1) // 换歌（此时上一轮上传仍在飞）

    pending.land?.({ attempt_id: 9, status: 'queued', progress: { done_lines: 0, total: 2 } })
    await vi.advanceTimersByTimeAsync(0)
    await p

    expect(play.status.value).toBeNull()
    expect(play.phase.value).toBe('idle')
    expect(play.detail.value).not.toBeNull() // 新歌详情正常在位（没被旧回执连带清掉）
  })

  it('R3：报告态直接换歌 → status/result/phase 一并清空（修复前旧报告滞留）', async () => {
    const { useSingPlay } = await installMock()
    const play = useSingPlay()
    await play.loadSongs()
    await play.openSong(1)

    const p = play.submitAudio(new Blob(['x']))
    await vi.advanceTimersByTimeAsync(0)
    await p
    await vi.advanceTimersByTimeAsync(1600) // 首轮轮询 → done + result
    expect(play.phase.value).toBe('done')
    expect(play.result.value?.overall).toBe(91.1)

    await play.openSong(1) // 报告态直接换歌
    expect(play.result.value).toBeNull() // 修复前：旧报告仍挂在状态里（新歌标题下渲染旧成绩）
    expect(play.status.value).toBeNull()
    expect(play.phase.value).toBe('idle')
  })
})
