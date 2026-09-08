/**
 * 阅读器 · 查词卡逻辑（docs/45 §6）：点词 → 45003 未收录降级 / 词形→头词 / 加生词本。
 * 与 MobileWordCard（展示层）解耦：本模块纯状态管理，视图挂接。
 */
import { reactive } from 'vue'

import { ApiError } from '@/api/client'
import { addVocab, lookupWord } from '@/api/reading'
import type { WordLookupResult } from '@/api/reading'

export function useWordLookup() {
  const state = reactive({
    open: false,
    loading: false,
    missing: false,
    result: null as WordLookupResult | null,
    word: '',
    context: '',
    /** 该词所在句子 idx（句子级动作「高亮这句/批注这句」用；无法定位时为 null） */
    sentenceIdx: null as number | null,
  })

  async function openFor(word: string, contextSentence: string, sentenceIdx: number | null = null) {
    if (!word) return
    state.word = word
    state.context = contextSentence
    state.sentenceIdx = sentenceIdx
    state.open = true
    state.loading = true
    state.missing = false
    state.result = null
    try {
      state.result = await lookupWord(word)
    } catch (e) {
      state.missing = e instanceof ApiError && e.code === 45003
    } finally {
      state.loading = false
    }
  }

  function close() {
    state.open = false
  }

  async function addToVocab(
    ctx: { bookId: number; chapterId: number },
  ): Promise<boolean> {
    if (!state.word) return false
    try {
      await addVocab(state.word, {
        book_id: ctx.bookId || undefined,
        chapter_id: ctx.chapterId,
        context: state.context.slice(0, 500),
      })
      state.open = false
      return true
    } catch {
      return false
    }
  }

  return { state, openFor, close, addToVocab }
}
