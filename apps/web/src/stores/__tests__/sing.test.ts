/**
 * 唱吧选曲 store（2026-09-21）——「当前跟唱歌曲」跨模块同步的单一真源。
 *
 * 覆盖：
 * - `loadSongs()` 写入列表并置 ready；**幂等**（ready 后二次调用不再发请求，三处调用者共用一份）；
 * - `force=true` 强制重拉（失败重试入口）；
 * - 失败写 `songsError` + failed，且**不清空**已拿到的列表；
 * - `selectSong()` 只翻 id，`currentSong` 由列表派生（id 不在列表里 → null）。
 *
 * 修复前必失败证据：本文件对应实现不存在（无 `stores/sing.ts`），
 * 选中态只存在于 `useSingPlay()` 实例内部，任何跨模块读取都拿不到。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { fetchSongs } from '@/api/sing'
import { ApiError } from '@/api/client'
import { useSingStore } from '@/stores/sing'
import type { SongSummary } from '@/api/sing'

vi.mock('@/api/sing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/sing')>()
  return { ...actual, fetchSongs: vi.fn() }
})

const mockedFetchSongs = vi.mocked(fetchSongs)

function song(id: number, over: Partial<SongSummary> = {}): SongSummary {
  return {
    id,
    title: `曲目 ${id}`,
    artist: 'Traditional · 合成旋律（公有领域童谣）',
    level: 1,
    duration_s: 30,
    bpm: 100,
    musical_key: 'C',
    cover_url: null,
    audio_url: null,
    pitch_ref_status: 'ready',
    expected_lines: 4,
    favorited: false,
    ...over,
  } as SongSummary
}

describe('useSingStore（选曲真源）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockedFetchSongs.mockReset()
  })

  it('loadSongs 写入列表并置 ready', async () => {
    mockedFetchSongs.mockResolvedValue([song(1), song(2)])
    const store = useSingStore()

    expect(store.songsStatus).toBe('idle')
    await store.loadSongs()

    expect(store.songsStatus).toBe('ready')
    expect(store.songs.map((s) => s.id)).toEqual([1, 2])
    expect(mockedFetchSongs).toHaveBeenCalledTimes(1)
  })

  it('幂等：ready 后二次调用不再发请求；force=true 才重拉', async () => {
    mockedFetchSongs.mockResolvedValue([song(1)])
    const store = useSingStore()

    await store.loadSongs()
    await store.loadSongs()
    expect(mockedFetchSongs).toHaveBeenCalledTimes(1)

    await store.loadSongs(true)
    expect(mockedFetchSongs).toHaveBeenCalledTimes(2)
  })

  it('失败：置 failed + 写可读文案（错误码映射），且不清空已有列表', async () => {
    mockedFetchSongs.mockResolvedValueOnce([song(1)])
    const store = useSingStore()
    await store.loadSongs()

    mockedFetchSongs.mockRejectedValueOnce(new ApiError(50002, '内部错误', 500))
    await store.loadSongs(true)

    expect(store.songsStatus).toBe('failed')
    expect(store.songsError).toBe('服务暂时异常，请稍后重试')
    expect(store.songs.map((s) => s.id)).toEqual([1]) // 旧列表仍在
  })

  it('selectSong → currentSong 命中；未选/不在列表 → null', async () => {
    mockedFetchSongs.mockResolvedValue([song(1, { title: 'Twinkle' }), song(7)])
    const store = useSingStore()

    expect(store.currentSong).toBeNull() // 未选
    await store.loadSongs()

    store.selectSong(7)
    expect(store.currentSongId).toBe(7)
    expect(store.currentSong?.id).toBe(7)

    store.selectSong(999) // 不在列表里的 id
    expect(store.currentSong).toBeNull()
  })
})