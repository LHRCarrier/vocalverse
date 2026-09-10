/**
 * 阅读器 · 听书装配（2026-09-09 抽离，让 MobileReaderView 守住 fe-08 的 350 行门禁）：
 * 把「句级播放（useChapterTts）+ 整章预合成（useChapterPrep）+ 听书条开关」收成一处，
 * 视图只消费 `ttsActive / progressLabel / openTts / closeTts` 与模板需要的播放态。
 *
 * 口径（docs/45 §5）：
 * · 打开听书条**不**立刻整章预合成——只有 prep 处于 idle/failed 才启动（避免重复任务 45006）；
 * · 单句模式（playOne）只播这一句，播完即止，不进连续播放（2026-09-10 组长反馈）。
 */
import { computed, ref } from 'vue'

import { useChapterPrep } from '@/composables/useChapterPrep'
import { useChapterTts } from '@/composables/useChapterTts'

import type { ReadingSentence } from '@/api/reading'

export function useReaderTts(
  chapterId: number,
  getChapterId: () => number | null,
  getSentences: () => ReadingSentence[],
) {
  const ttsActive = ref(false)
  const tts = useChapterTts(chapterId, getSentences)
  const { prepState, start: startPrep } = useChapterPrep()

  const ttsState = tts.state
  const ttsProgress = tts.progress
  const ttsRate = tts.rate
  const ttsError = tts.errorText
  const ttsVoice = tts.voice
  const ttsCurrentIdx = tts.currentIdx

  const progressLabel = computed(() => {
    const total = getSentences().length
    return total ? `${Math.min(ttsCurrentIdx.value + 1, total)}/${total}` : '听书'
  })

  /** 打开听书条（必要时启动整章预合成；单句播放由 playOne 单独控制） */
  function openTts(): void {
    const id = getChapterId()
    if (id == null) return
    ttsActive.value = true
    if (prepState.status === 'idle' || prepState.status === 'failed') {
      startPrep(id, ttsVoice.value)
    }
  }

  /** 关闭听书条（原生返回手势的最后一层） */
  function closeTts(): void {
    tts.stop()
    ttsActive.value = false
  }

  /** 只显示听书条并播这一句（不整章预合成） */
  function playOne(idx: number): void {
    ttsActive.value = true
    void tts.playOne(idx)
  }

  return {
    ttsActive,
    tts,
    prepState,
    progressLabel,
    ttsState,
    ttsProgress,
    ttsRate,
    ttsError,
    ttsVoice,
    ttsCurrentIdx,
    openTts,
    closeTts,
    playOne,
  }
}
