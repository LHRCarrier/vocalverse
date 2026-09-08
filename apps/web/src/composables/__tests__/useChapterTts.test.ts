/**
 * 听书播放器 · 单句模式（2026-09-10 组长实测反馈：「听这句」应从该句播到章末，应只读这一句）。
 * 用实际播放次数（Audio.play）区分：单句模式播完即止；章节模式每句 ended 自动进下一句。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

const fake = vi.hoisted(() => ({
  endedHandler: null as (() => void) | null,
  plays: [] as string[],
}))

vi.mock('@/api/reading', () => ({
  loadSegmentAudio: vi.fn(async () => new Blob(['x'])),
}))

import { useChapterTts } from '@/composables/useChapterTts'
import type { ReadingSentence } from '@/api/reading'

const SENTENCES: ReadingSentence[] = [
  { idx: 0, text: 'a', para_idx: 0, start: 0, end: 1 },
  { idx: 1, text: 'b', para_idx: 0, start: 2, end: 3 },
  { idx: 2, text: 'c', para_idx: 0, start: 4, end: 5 },
]

const origAudio = globalThis.Audio
const origCreate = URL.createObjectURL
const origRevoke = URL.revokeObjectURL

beforeEach(() => {
  fake.endedHandler = null
  fake.plays.length = 0
  URL.createObjectURL = () => 'blob:x'
  URL.revokeObjectURL = () => undefined
  vi.stubGlobal(
    'Audio',
    class {
      src = ''
      playbackRate = 1
      addEventListener(type: string, cb: () => void) {
        if (type === 'ended') fake.endedHandler = cb
      }
      play() {
        fake.plays.push(this.src)
        return Promise.resolve()
      }
      pause() {}
      removeAttribute() {}
    },
  )
})

afterEach(() => {
  globalThis.Audio = origAudio
  URL.createObjectURL = origCreate
  URL.revokeObjectURL = origRevoke
})

describe('useChapterTts 单句/章节模式', () => {
  it('playOne(0)：本句播完即止，不自动连播下一句', async () => {
    const tts = useChapterTts(1, () => SENTENCES)
    await tts.playOne(0)
    expect(fake.plays).toHaveLength(1)

    fake.endedHandler?.() // 本句播放结束
    await flushPromises()
    expect(tts.state.value).toBe('ended')
    expect(fake.plays).toHaveLength(1) // 没有再播下一句
  })

  it('playFrom(0)（章节模式）：每句 ended 自动进下一句，直到末句', async () => {
    const tts = useChapterTts(1, () => SENTENCES)
    await tts.playFrom(0)
    expect(fake.plays).toHaveLength(1)
    expect(tts.currentIdx.value).toBe(0)

    fake.endedHandler?.()
    await flushPromises()
    expect(tts.currentIdx.value).toBe(1)
    expect(fake.plays).toHaveLength(2)

    fake.endedHandler?.()
    await flushPromises()
    expect(tts.currentIdx.value).toBe(2)
    expect(fake.plays).toHaveLength(3)

    fake.endedHandler?.()
    await flushPromises()
    expect(tts.state.value).toBe('ended')
    expect(fake.plays).toHaveLength(3)
  })

  it('单句播完后按 ▶ 重播：仍是单句（不再连播下一句）', async () => {
    const tts = useChapterTts(1, () => SENTENCES)
    await tts.playOne(0)
    expect(fake.plays).toHaveLength(1)

    fake.endedHandler?.() // 单句播完结束
    await flushPromises()
    expect(tts.state.value).toBe('ended')

    await tts.toggle() // ▶ 重播
    expect(fake.plays).toHaveLength(2)
    expect(tts.state.value).toBe('playing')

    fake.endedHandler?.() // 重播结束：应为单句，不自动进下一句
    await flushPromises()
    expect(fake.plays).toHaveLength(2)
    expect(tts.state.value).toBe('ended')
  })

  it('章节模式 pause→resume 重播：仍是整章连播', async () => {
    const tts = useChapterTts(1, () => SENTENCES)
    await tts.playFrom(0) // plays=1, lastSingle=false
    await tts.toggle() // ▶ 暂停
    expect(tts.state.value).toBe('paused')
    await tts.toggle() // ▶ 恢复 → playFrom(0, false)（章节模式）
    expect(tts.state.value).toBe('playing')
    expect(fake.plays).toHaveLength(2)

    fake.endedHandler?.() // 恢复后播完：章节模式 → 自动进下一句
    await flushPromises()
    expect(tts.currentIdx.value).toBe(1)
    expect(fake.plays).toHaveLength(3)
  })
})
