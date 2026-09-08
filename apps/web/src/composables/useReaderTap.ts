/**
 * 阅读器正文点击语义（2026-09-10 组长拍板）：
 *   单击词   → 查词卡（释义 + 加入生词本）
 *   单击句子 → 选中该句（再点取消），底部动作条决定「高亮 / 批注 / 听这句」
 *   听书进行中单击句子 → 从该句续播（保持原行为）
 *   长按划选 → 仍走 selectionchange 的自由区间批注（高级用法，保留）
 * 抽到 composable 的原因：MobileReaderView 有 350 行门禁（fe-08），点击分发占 40+ 行。
 */
import { ref } from 'vue'

import type { AnnotationItem, ReadingSentence } from '@/api/reading'

export interface ReaderTapDeps {
  getSentence: (idx: number) => ReadingSentence | undefined
  /** 打开查词卡 */
  openWord: (word: string, contextSentence: string) => void
  /** 按批注 id 打开批注查看弹层 */
  openNoteById: (id: number) => void
  /** 当前批注列表（取被点段落的批注用） */
  annotations: { value: AnnotationItem[] }
  ttsState: { value: string }
  ttsCurrentIdx: { value: number }
  playFrom: (idx: number) => void
}

export function useReaderTap(deps: ReaderTapDeps) {
  /** 当前选中的句子 idx（null = 未选中） */
  const selIdx = ref<number | null>(null)

  function clearSelection(): void {
    selIdx.value = null
  }

  function onReaderClick(e: MouseEvent): void {
    const target = e.target as HTMLElement

    // ① 笔记角标 → 看笔记（优先于查词：角标常落在词上）
    const markEl = target.closest('.u-rd__annmark') as HTMLElement | null
    if (markEl?.dataset.ann) {
      clearSelection()
      deps.openNoteById(Number(markEl.dataset.ann))
      return
    }

    const segEl = target.closest('.u-rd__seg') as HTMLElement | null
    const sentenceEl = target.closest('.u-rd__sentence') as HTMLElement | null

    // ② 词段 → 查词卡（任何词都可查）
    const word = segEl?.dataset.word ?? ''
    if (word) {
      clearSelection()
      const idx = Number(sentenceEl?.dataset.idx ?? -1)
      deps.openWord(word, idx >= 0 ? (deps.getSentence(idx)?.text ?? '') : '')
      return
    }

    // ③ 非词批注段（标点/空格被批注）→ 看批注
    if (segEl?.dataset.ann) {
      clearSelection()
      deps.openNoteById(Number(segEl.dataset.ann))
      return
    }

    if (!sentenceEl) {
      clearSelection()
      return
    }
    const idx = Number(sentenceEl.dataset.idx ?? -1)
    if (idx < 0) return

    // ④ 听书进行中：点句子 = 从该句续播
    if (deps.ttsState.value !== 'idle') {
      clearSelection()
      if (idx !== deps.ttsCurrentIdx.value) deps.playFrom(idx)
      return
    }

    // ⑤ 非听书态：选中/取消选中该句（动作条随后出现）
    selIdx.value = selIdx.value === idx ? null : idx
  }

  return { selIdx, clearSelection, onReaderClick }
}
