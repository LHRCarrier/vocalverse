/**
 * 阅读器 · 生词标记集合（已加入生词本的词在正文里打淡黄下划线）。
 * 抽到 composable 的原因：MobileReaderView 有 350 行门禁（fe-08）。
 */
import { ref } from 'vue'

import { fetchVocab } from '@/api/reading'
import { vocabWordSet } from '@/audio/reader-words'

export function useReaderVocab() {
  const vocabWords = ref<Set<string>>(new Set())

  async function refreshVocab(): Promise<void> {
    try {
      const res = await fetchVocab()
      vocabWords.value = vocabWordSet(res.items)
    } catch {
      /* 生词标记非关键路径 */
    }
  }

  return { vocabWords, refreshVocab }
}
