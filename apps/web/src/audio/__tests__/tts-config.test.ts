import { describe, expect, it } from 'vitest'
import { DEFAULT_TTS_RATE, DEFAULT_TTS_VOICE } from '@/audio/tts-config'

/**
 * 默认音色单一真源锁（2026-09 ASR/TTS 可插拔重构）。
 *
 * 这两个值必须与后端 `services/python/app/audio/voices.py` 的
 * `DEFAULT_VOICE` / `DEFAULT_RATE` 一致：不一致时前端会请求一个后端认为"非默认"的音色，
 * 缓存键随之分裂（同一句话在 edge 档下被合成两次）。
 *
 * 本用例不是"测实现"，而是把**跨端一致性**变成一条会红的断言 —— 改这里就必须同步后端。
 */
describe('tts-config（默认 TTS 参数跨端一致）', () => {
  it('默认音色为 edge 在线档的 Jenny', () => {
    expect(DEFAULT_TTS_VOICE).toBe('en-US-JennyNeural')
  })

  it('默认语速为 edge 记法的 +0%', () => {
    expect(DEFAULT_TTS_RATE).toBe('+0%')
  })

  it('默认音色是 BCP-47 区域码形式（后端音色目录同形）', () => {
    expect(DEFAULT_TTS_VOICE).toMatch(/^[a-z]{2}-[A-Z]{2}-/)
  })
})
