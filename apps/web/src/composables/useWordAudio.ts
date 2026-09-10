/**
 * 阅读器 · 查词卡的「朗读」播放（2026-09-10 修复：词卡 @play-word 被接成 void 0，点读不出声）。
 * 词读音端点带 Bearer 鉴权（docs/06 §11），原生 Audio 直连 URL 会 401 → 走 loadAudioBlob 取 blob
 * + useBlobAudio 管理 objectURL 生命周期（防 Blob 泄漏）。
 */
import { shallowRef } from 'vue'

import { loadAudioBlob } from '@/api/client'
import { wordAudioUrl } from '@/api/reading'
import { useBlobAudio } from '@/composables/useBlobAudio'

export function useWordAudio() {
  const audio = shallowRef<HTMLAudioElement | null>(null)
  const { createUrl, revokeUrl } = useBlobAudio()

  async function play(word: string): Promise<boolean> {
    if (!word) return false
    try {
      const blob = await loadAudioBlob(wordAudioUrl(word))
      const url = createUrl(blob)
      audio.value?.pause()
      const el = new Audio(url)
      el.onended = () => {
        revokeUrl(url)
        audio.value = null
      }
      void el.play().catch(() => undefined)
      audio.value = el
      return true
    } catch {
      return false
    }
  }

  return { play }
}
