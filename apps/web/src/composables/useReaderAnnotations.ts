/**
 * 阅读器 · 划词批注逻辑（docs/45 §6 · v1 句内划选）：选区 → 高亮/笔记 → 列表/跳转/删除。
 * 2026-09-10 扩展（组长手机实测 bug2）：跳转后必须看得见批注 → 本模块同时持有
 * 「单条批注查看弹层」状态与跳转闪烁，视图只管渲染。
 */
import { onBeforeUnmount, reactive, ref } from 'vue'

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
  /** 单条批注查看弹层（点正文批注段/角标、或列表跳转后自动打开） */
  const noteSheet = reactive({ open: false, item: null as AnnotationItem | null })
  /** 跳转后闪烁的批注 id（1.8s 后清除） */
  const flashAnnId = ref<number | null>(null)
  let flashTimer: ReturnType<typeof setTimeout> | null = null

  function openNote(ann: AnnotationItem | null): void {
    if (!ann) return
    noteSheet.item = ann
    noteSheet.open = true
  }

  function openNoteById(id: number): void {
    openNote(annotations.value.find((a) => a.id === id) ?? null)
  }

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

  /**
   * 整句批注入口（2026-09-10 组长实测：批注 = 读者对某句/某段的理解，
   * 不该强制长按划词）——点句子即选中该句，范围 = 整句。
   */
  function createForSentence(sentenceIdx: number): boolean {
    const sentence = getChapter()?.sentences[sentenceIdx]
    if (!sentence) return false
    annSheet.sentenceIdx = sentenceIdx
    annSheet.relStart = 0
    annSheet.relEnd = sentence.text.length
    annSheet.snippet = sentence.text.slice(0, 300)
    annSheet.open = true
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
      noteSheet.open = false
      noteSheet.item = null
    } catch {
      /* 非关键 */
    }
  }

  /** 列表点跳转：滚到该句 + 闪烁 + 直接弹出批注内容（修复前只滚动，看不到批注） */
  function jump(a: AnnotationItem): void {
    annListOpen.value = false
    if (a.sentence_idx != null) {
      onJump(a.sentence_idx)
    } else {
      const sentence = getChapter()?.sentences.find((s) => a.start_offset >= s.start && a.start_offset < s.end)
      if (sentence) onJump(sentence.idx)
    }
    flashAnnId.value = a.id
    if (flashTimer) clearTimeout(flashTimer)
    flashTimer = setTimeout(() => {
      flashAnnId.value = null
    }, 1800)
    openNote(a)
  }

  onBeforeUnmount(() => {
    if (flashTimer) clearTimeout(flashTimer)
  })

  return {
    annotations,
    annSheet,
    annListOpen,
    noteSheet,
    flashAnnId,
    refresh,
    createFromSelection,
    createForSentence,
    save,
    remove,
    jump,
    openNote,
    openNoteById,
  }
}
