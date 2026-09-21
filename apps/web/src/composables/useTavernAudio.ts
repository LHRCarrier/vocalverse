/**
 * 酒馆音频（TRPG）：单元素串行播音器 + 逐句音频队列 + 重听。
 *
 * 背景（与 MobileSpeakingView 同口径，2026-09-07）：同一 mp3 URL 缓存命中时 metadata
 * 会提前就绪，旧「每 chunk 一个 Audio + 各自定时器」会抢跑叠音；单元素 + ended 驱动严格
 * 串行。播放必须走 loadAudioBlob（GET /audio 要 Bearer，原生 <audio> 不带 Authorization）。
 */
import { ref } from 'vue'

import { loadAudioBlob } from '@/api/client'
import { tts } from '@/api/tts'
import { useBlobAudio } from '@/composables/useBlobAudio'

export function useTavernAudio() {
  const speaker = new Audio()
  const { createUrl, revokeUrl, releaseAll } = useBlobAudio()
  const playingIndex = ref<number | null>(null)
  let queue: string[] = []
  let pumping = false

  function flush() {
    speaker.pause()
    speaker.onended = null
    pumping = false
    queue = []
  }

  function pump() {
    if (pumping) return
    const url = queue.shift()
    if (!url) return
    pumping = true
    void loadAudioBlob(url)
      .then((blob) => {
        if (!blob.size) throw new Error('empty audio')
        const objectUrl = createUrl(blob)
        speaker.src = objectUrl
        speaker.onended = () => {
          revokeUrl(objectUrl)
          pumping = false
          pump()
        }
        return speaker.play()
      })
      .catch((err) => {
        console.warn('[tavern] chunk playback failed:', err)
        pumping = false
        pump()
      })
  }

  function queueChunk(url: string) {
    queue.push(url)
    pump()
  }

  /** 重听（点击时实时合成；与队列互斥，避免叠音） */
  async function replay(index: number, text: string) {
    if (!text) return
    if (playingIndex.value === index) {
      flush()
      playingIndex.value = null
      return
    }
    flush()
    try {
      const blob = await tts(text)
      if (!blob.size) return
      const url = createUrl(blob)
      speaker.src = url
      playingIndex.value = index
      speaker.onended = () => {
        revokeUrl(url)
        if (playingIndex.value === index) playingIndex.value = null
      }
      await speaker.play()
    } catch {
      playingIndex.value = null
    }
  }

  return { playingIndex, flush, queueChunk, replay, releaseAll }
}

export type TavernAudio = ReturnType<typeof useTavernAudio>
