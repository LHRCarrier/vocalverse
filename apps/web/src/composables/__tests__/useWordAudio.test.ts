/**
 * 查词卡「朗读」播放（2026-09-10 修复：@play-word 原接 void 0，点读不出声）。
 * 词读音端点带 Bearer（docs/06 §11）→ 必须 loadAudioBlob（带 token），原生 Audio 直连会 401。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/client', () => ({
  loadAudioBlob: vi.fn(async () => new Blob(['x'])),
}))
vi.mock('@/api/reading', () => ({
  wordAudioUrl: vi.fn((w: string) => `/word/${w}`),
}))

import { useWordAudio } from '@/composables/useWordAudio'
import { loadAudioBlob } from '@/api/client'
import { wordAudioUrl } from '@/api/reading'

describe('useWordAudio', () => {
  const plays: string[] = []
  const origAudio = globalThis.Audio
  const origCreate = URL.createObjectURL
  const origRevoke = URL.revokeObjectURL

  beforeEach(() => {
    plays.length = 0
    vi.clearAllMocks()
    URL.createObjectURL = () => 'blob:mock'
    URL.revokeObjectURL = () => undefined
    vi.stubGlobal(
      'Audio',
      class {
        src = ''
        onended: (() => void) | null = null
        constructor(src = '') {
          this.src = src
        }
        play() {
          plays.push(this.src)
          return Promise.resolve()
        }
      },
    )
  })

  afterEach(() => {
    globalThis.Audio = origAudio
    URL.createObjectURL = origCreate
    URL.revokeObjectURL = origRevoke
    vi.useRealTimers()
  })

  it('play(word) → loadAudioBlob 取带 token 的 blob 并 new Audio(url).play()', async () => {
    const { play } = useWordAudio()
    const ok = await play('Alice')

    expect(ok).toBe(true)
    expect(wordAudioUrl).toHaveBeenCalledWith('Alice')
    expect(loadAudioBlob).toHaveBeenCalledWith('/word/Alice')
    expect(plays).toEqual(['blob:mock'])
  })

  it('空词 → 不请求', async () => {
    const { play } = useWordAudio()
    expect(await play('')).toBe(false)
    expect(loadAudioBlob).not.toHaveBeenCalled()
  })

  it('加载失败 → 返回 false（不崩溃）', async () => {
    vi.mocked(loadAudioBlob).mockRejectedValueOnce(new Error('401'))
    const { play } = useWordAudio()
    expect(await play('Alice')).toBe(false)
  })
})
