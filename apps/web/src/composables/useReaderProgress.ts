/**
 * 阅读器 · 进度保存与定位（docs/45 §6）：滚动防抖 1s + 退出 flush；章节内 char offset 为主锚。
 */
import { onBeforeUnmount, type Ref } from 'vue'

import { saveProgress } from '@/api/reading'
import type { ReadingChapter } from '@/api/reading'

export function useReaderProgress(
  bookId: number,
  chapterId: number,
  mainEl: Ref<HTMLElement | null>,
  getChapter: () => ReadingChapter | null,
) {
  const posKey = `vv_rd_pos_${chapterId}`
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function scrollToSentence(idx: number): void {
    const el = mainEl.value?.querySelector(`[data-idx="${idx}"]`)
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }

  function visibleOffset(): number {
    const chapter = getChapter()
    if (!chapter || !mainEl.value) return 0
    let best = 0
    for (const s of chapter.sentences.slice(0, 40)) {
      const el = mainEl.value.querySelector(`[data-idx="${s.idx}"]`)
      if (!el) continue
      const rect = (el as HTMLElement).getBoundingClientRect()
      if (rect.top < window.innerHeight * 0.6) best = s.start
    }
    return best
  }

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => void flush(), 1000)
  }

  async function flush(): Promise<void> {
    const chapter = getChapter()
    if (!chapter) return
    try {
      await saveProgress(bookId, chapterId, visibleOffset())
    } catch {
      /* 静默 */
    }
  }

  function restore(): void {
    const saved = Number(localStorage.getItem(posKey) ?? 0)
    if (saved > 0) scrollToSentence(saved)
  }

  onBeforeUnmount(() => {
    if (saveTimer) clearTimeout(saveTimer)
    void flush()
    localStorage.setItem(posKey, String(visibleOffset()))
  })

  return { scrollToSentence, scheduleSave, flush, restore }
}
