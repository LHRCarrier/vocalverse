/**
 * 酒馆音频（TRPG）：单元素串行播音器 + 逐句音频队列 + 卡拉OK式逐词高亮 + 单句重听。
 *
 * 高亮原理（与 QQ 音乐歌词一致）：服务端每个 audio_chunk 带 `text`（本句原文）与
 * `offset`（该句在 DM 整段内容里的字符偏移）；播放该句时按 `currentTime / duration`
 * 推进，前端把句子 token 化后按进度点亮。**句子音频时长 = 音频元素实测时长**（更准），
 * chunk.duration 仅作元素元数据未就绪时的兜底。
 *
 * 背景（与 MobileSpeakingView 同口径，2026-09-07）：同一 mp3 URL 缓存命中时 metadata
 * 会提前就绪，旧「每 chunk 一个 Audio + 各自定时器」会抢跑叠音；单元素 + ended 驱动严格
 * 串行。播放必须走 loadAudioBlob（GET /audio 要 Bearer，原生 <audio> 不带 Authorization）。
 */
import { ref, type Ref } from 'vue'

import { loadAudioBlob } from '@/api/client'
import { tts } from '@/api/tts'
import { useBlobAudio } from '@/composables/useBlobAudio'

interface QueueItem {
  url: string
  /** 行下标（消息流中的第 N 条） */
  rowIndex: number
  /** 本句原文（高亮定位用；手动重听为整条消息，可为 null） */
  text: string | null
  /** 本句在整段内容里的字符偏移 */
  offset: number | null
  /** 服务端估算时长（秒；兜底用） */
  duration: number | null
}

export interface TavernHighlight {
  rowIndex: number
  /** 当前句字符偏移（未分句的手动重听为 null） */
  offset: number | null
  /** 当前句字符数（未分句为 null） */
  length: number | null
  /** 句内进度 0~1 */
  progress: number
}

export function useTavernAudio() {
  const speaker = new Audio()
  const { createUrl, revokeUrl, releaseAll } = useBlobAudio()
  const playingIndex: Ref<number | null> = ref(null)
  /** 当前朗读高亮（逐词变亮）；null = 未在播 */
  const highlight: Ref<TavernHighlight | null> = ref(null)
  let queue: QueueItem[] = []
  let pumping = false
  let fallbackTimer: ReturnType<typeof setTimeout> | null = null

  function clearFallback() {
    if (fallbackTimer != null) {
      clearTimeout(fallbackTimer)
      fallbackTimer = null
    }
  }

  function flush() {
    speaker.pause()
    speaker.onended = null
    speaker.ontimeupdate = null
    clearFallback()
    pumping = false
    queue = []
    highlight.value = null
  }

  function updateProgress(current: QueueItem) {
    const total = Number.isFinite(speaker.duration) && speaker.duration > 0
      ? speaker.duration
      : (current.duration ?? 0)
    const progress = total > 0 ? Math.min(1, speaker.currentTime / total) : 0
    highlight.value = {
      rowIndex: current.rowIndex,
      offset: current.offset,
      length: current.text ? current.text.length : null,
      progress,
    }
  }

  function pump() {
    if (pumping) return
    const current = queue.shift()
    if (!current) {
      highlight.value = null
      return
    }
    pumping = true
    void loadAudioBlob(current.url)
      .then((blob) => {
        if (!blob.size) throw new Error('empty audio')
        const objectUrl = createUrl(blob)
        speaker.src = objectUrl
        speaker.currentTime = 0
        updateProgress(current)
        speaker.ontimeupdate = () => updateProgress(current)
        const finish = () => {
          speaker.ontimeupdate = null
          speaker.onended = null
          clearFallback()
          revokeUrl(objectUrl)
          pumping = false
          pump()
        }
        speaker.onended = finish
        // 兜底：ended 不触发（headless/无音频设备）时按时长收尾
        const ms = (Number.isFinite(speaker.duration) && speaker.duration > 0
          ? speaker.duration * 1000
          : (current.duration ?? 6) * 1000) + 600
        clearFallback()
        fallbackTimer = setTimeout(finish, Math.min(ms, 120_000))
        return speaker.play()
      })
      .catch((err) => {
        console.warn('[tavern] chunk playback failed:', err)
        pumping = false
        pump()
      })
  }

  /** 入队一个服务端音频块（服务端保证按句顺序下发） */
  function queueChunk(url: string, rowIndex: number, text?: string | null, offset?: number | null, duration?: number | null) {
    queue.push({ url, rowIndex, text: text ?? null, offset: offset ?? null, duration: duration ?? null })
    pump()
  }

  /** 单句/整条重听（长按菜单「听这句」）：立即接管播放器并同步高亮 */
  async function replay(rowIndex: number, text: string, offset: number | null = null) {
    if (!text) return
    if (playingIndex.value === rowIndex && speaker.src) {
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
      playingIndex.value = rowIndex
      const current: QueueItem = { url, rowIndex, text, offset, duration: null }
      updateProgress(current)
      speaker.ontimeupdate = () => updateProgress(current)
      speaker.onended = () => {
        speaker.ontimeupdate = null
        revokeUrl(url)
        highlight.value = null
        if (playingIndex.value === rowIndex) playingIndex.value = null
      }
      await speaker.play()
    } catch {
      playingIndex.value = null
      highlight.value = null
    }
  }

  /** 停止当前朗读（长按菜单/关语音时调用） */
  function stop() {
    flush()
    playingIndex.value = null
  }

  return { playingIndex, highlight, queueChunk, replay, stop, flush, releaseAll }
}

export type TavernAudio = ReturnType<typeof useTavernAudio>
