/**
 * 阅读器 · 查词卡与词音装配（2026-09-09 抽离，让 MobileReaderView 守住 fe-08 的 350 行门禁）。
 *
 * - `useWordLookup`：查词状态机（点词 → 45003 降级 / 词形→头词 / 加生词本）；
 * - `useWordAudio`：词读音（端点需带 token → 走 blob 管道，不能直接用 `<audio src>`）；
 * - 本模块只把两者与 toast 反馈接起来，视图消费 `wordLookup` 与两个动作。
 */
import { useWordAudio } from '@/composables/useWordAudio'
import { useWordLookup } from '@/composables/useWordLookup'
import { useUiStore } from '@/stores/ui'

export function useReaderWordUi(bookId: number, chapterId: number, onVocabAdded?: () => Promise<void>) {
  const ui = useUiStore()
  const wordLookup = useWordLookup()
  const { play: playWordAudio } = useWordAudio()

  async function addWordToVocab(): Promise<void> {
    const ok = await wordLookup.addToVocab({ bookId, chapterId, scene: 'reading' })
    ui.showToast(ok ? '已加入生词本' : '加入失败')
    if (ok && onVocabAdded) await onVocabAdded()
  }

  async function playWord(): Promise<void> {
    const word = wordLookup.state.word
    if (!word) return
    const ok = await playWordAudio(word)
    if (!ok) ui.showToast('读音播放失败')
  }

  return { wordLookup, addWordToVocab, playWord }
}
