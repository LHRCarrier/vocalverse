/**
 * 阅读器 · 划词批注逻辑（docs/45 §6 · v1 句内划选）：选区 → 高亮/笔记 → 列表/跳转/删除。
 */
import { reactive, ref } from 'vue'

import { createAnnotation, deleteAnnotation, fetchAnnotations } from '@/api/reading'
import type { AnnotationItem, ReadingChapter } from '@/api/reading'

export function useReaderAnnotations(
  chapterId: number,
  getChapter: () => ReadingChapter | null,
  onJump: (sentenceIdx: number) => void,
) {
  const annotations = ref<AnnotationItem[]>([])
  const annSheet = reactive({ open: false, snippet: '', relStart: 0, relEnd: 0, sentenceIdx: -1 })
  const annListOpen = ref(false)

  async function refresh(): Promise<void> {
    try {
      annotations.value = await fetchAnnotations(chapterId)
    } catch {
      /* 非关键 */
    }
  }

  /** selectionchange 落点：限制句内（跨句选区取交集由视图层保证——isCollapsed 后进入） */
  function createFromSelection(selection: Selection): boolean {
    const range = selection.getRangeAt(0)
    const anchor = range.commonAncestorContainer
    const sentenceEl = (
      anchor.parentElement ?? (anchor as HTMLElement)
    )?.closest('.u-rd__sentence') as HTMLElement | null
    if (!sentenceEl) return false
    const idx = Number(sentenceEl.dataset.idx ?? -1)
    const sentence = getChapter()?.sentences[idx]
    if (idx < 0 || !sentence) return false
    if (!sentenceEl.contains(range.startContainer) || !sentenceEl.contains(range.endContainer)) return false
    annSheet.sentenceIdx = idx
    annSheet.relStart = range.startOffset
    annSheet.relEnd = range.endOffset
    annSheet.snippet = String(selection.toString()).slice(0, 300)
    annSheet.open = true
    selection.removeAllRanges()
    return true
  }

  async function save(payload: { note: string; color: string }): Promise<boolean> {
    const sentence = getChapter()?.sentences[annSheet.sentenceIdx]
    const start = annSheet.relStart
    const end = annSheet.relEnd
    if (!sentence || end <= start) return false
    try {
      await createAnnotation({
        kind: payload.note ? 'note' : 'highlight',
        chapter_id: chapterId,
        start_offset: sentence.start + start,
        end_offset: sentence.start + end,
        text: annSheet.snippet,
        note: payload.note || undefined,
        color: payload.color,
        sentence_idx: annSheet.sentenceIdx,
      })
      annSheet.open = false
      await refresh()
      return true
    } catch {
      return false
    }
  }

  async function remove(id: number): Promise<void> {
    try {
      await deleteAnnotation(id)
      await refresh()
      annListOpen.value = false
    } catch {
      /* 非关键 */
    }
  }

  function jump(a: AnnotationItem): void {
    annListOpen.value = false
    if (a.sentence_idx != null) {
      onJump(a.sentence_idx)
      return
    }
    const sentence = getChapter()?.sentences.find((s) => a.start_offset >= s.start && a.start_offset < s.end)
    if (sentence) onJump(sentence.idx)
  }

  return { annotations, annSheet, annListOpen, refresh, createFromSelection, save, remove, jump }
}
