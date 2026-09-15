/**
 * 阅读器 · 划词批注逻辑（docs/45 §6 · v1 句内划选）：选区 → 高亮/笔记 → 列表/跳转/删除。
 * 2026-09-10 扩展（组长手机实测 bug2）：跳转后必须看得见批注 → 本模块同时持有
 * 「单条批注查看弹层」状态与跳转闪烁，视图只管渲染。
 * 2026-09-09 扩展（组长手机实测读书域系列 4 条 BUG）：
 *   · 「高亮这句」不再直出默认色 → annSheet.mode='highlight' 先出选色面板（chooseColorForSentence）；
 *   · 已批注句子可改色/改笔记 → update()（PATCH /annotations/{id}）；
 *   · 句首批注角标 → openSentence()：单条直开查看，多条开「本句批注」列表。
 */
import { computed, onBeforeUnmount, reactive, ref } from 'vue'

import { createAnnotation, deleteAnnotation, fetchAnnotations, patchAnnotation } from '@/api/reading'
import { safeAnnColor } from '@/audio/annotation-colors'
import type { AnnotationItem, ReadingChapter } from '@/api/reading'

/** 批注弹层模式：create=写批注（笔记可选）/ highlight=只选高亮色（先选后落） */
export type AnnSheetMode = 'create' | 'highlight'

export function useReaderAnnotations(
  chapterId: number,
  getChapter: () => ReadingChapter | null,
  onJump: (sentenceIdx: number) => void,
) {
  const annotations = ref<AnnotationItem[]>([])
  const annSheet = reactive({
    open: false,
    mode: 'create' as AnnSheetMode,
    snippet: '',
    relStart: 0,
    relEnd: 0,
    sentenceIdx: -1,
  })
  const annListOpen = ref(false)
  /** 单条批注查看弹层（点正文批注段/角标、或列表跳转后自动打开） */
  const noteSheet = reactive({ open: false, item: null as AnnotationItem | null })
  /** 本句批注列表（句首角标命中多条时打开；sentenceIdx=null 时为空） */
  const sentList = reactive({ open: false, sentenceIdx: -1 })
  /** 跳转后闪烁的批注 id（1.8s 后清除） */
  const flashAnnId = ref<number | null>(null)
  let flashTimer: ReturnType<typeof setTimeout> | null = null

  /** 本句批注列表内容（按起点排序；句首角标多条时用） */
  const sentListItems = computed<AnnotationItem[]>(() => {
    if (sentList.sentenceIdx < 0) return []
    const s = getChapter()?.sentences[sentList.sentenceIdx]
    if (!s) return []
    return annotations.value
      .filter((a) => a.start_offset < s.end && a.end_offset > s.start)
      .slice()
      .sort((x, y) => x.start_offset - y.start_offset)
  })

  /** 某句的全部批注（句首角标渲染用；空数组 = 该句无批注） */
  function annotationsOf(sentenceIdx: number): AnnotationItem[] {
    const s = getChapter()?.sentences[sentenceIdx]
    if (!s) return []
    return annotations.value
      .filter((a) => a.start_offset < s.end && a.end_offset > s.start)
      .slice()
      .sort((x, y) => x.start_offset - y.start_offset)
  }

  function openNote(ann: AnnotationItem | null): void {
    if (!ann) return
    noteSheet.item = ann
    noteSheet.open = true
  }

  function openNoteById(id: number): void {
    openNote(annotations.value.find((a) => a.id === id) ?? null)
  }

  /**
   * 句首批注角标入口（修复「查看已批注句子困难」）：
   * 1 条 → 直接看内容；多条 → 开本句批注列表（避免只给第一条、其余永远看不到）。
   */
  function openSentence(sentenceIdx: number): void {
    const list = annotationsOf(sentenceIdx)
    if (list.length === 0) return
    if (list.length === 1) {
      openNote(list[0])
      return
    }
    sentList.sentenceIdx = sentenceIdx
    sentList.open = true
  }

  async function refresh(): Promise<void> {
    try {
      annotations.value = await fetchAnnotations(chapterId)
    } catch {
      /* 非关键 */
    }
  }

  /**
   * 选区端点 → 句内相对偏移。
   * 2026-09-09 修复：原先直接用 `range.startOffset/endOffset`，而这两个值是**相对选区容器
   * 文本节点**的，不是相对句子——句内嵌套 span（词块）时偏移会偏小，批注落到错误位置
   * （跨段选区还会静默失败）。改用 Range 前缀长度法：`[句首, 端点)` 的文本长度即句内偏移。
   */
  function offsetWithin(root: HTMLElement, node: Node, offset: number): number {
    const r = document.createRange()
    r.setStart(root, 0)
    try {
      r.setEnd(node, offset)
    } catch {
      return -1 // 端点不在该句内
    }
    return r.toString().length
  }

  /** selectionchange 落点：限制句内（跨句选区忽略——v1 只做句内批注，docs/45 §6） */
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
    const relStart = offsetWithin(sentenceEl, range.startContainer, range.startOffset)
    const relEnd = offsetWithin(sentenceEl, range.endContainer, range.endOffset)
    if (relStart < 0 || relEnd <= relStart) return false
    annSheet.mode = 'create'
    annSheet.sentenceIdx = idx
    annSheet.relStart = relStart
    annSheet.relEnd = relEnd
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
    annSheet.mode = 'create'
    annSheet.sentenceIdx = sentenceIdx
    annSheet.relStart = 0
    annSheet.relEnd = sentence.text.length
    annSheet.snippet = sentence.text.slice(0, 300)
    annSheet.open = true
    return true
  }

  /**
   * 整句高亮 · 先选色（2026-09-09 修复组长实测「点高亮这句不等选色就默认第一个颜色」）：
   * 只开选色面板，不写库——用户在面板里明确点一个色再保存。
   * 需要「色点直出」（动作条色点）时走 highlightSentence(idx, color)。
   */
  function chooseColorForSentence(sentenceIdx: number): boolean {
    if (!createForSentence(sentenceIdx)) return false
    annSheet.mode = 'highlight'
    return true
  }

  /** 整句快速高亮（动作条色点直出：色点本身即选色，不弹层） */
  async function highlightSentence(sentenceIdx: number, color: string): Promise<boolean> {
    if (!createForSentence(sentenceIdx)) return false
    return await save({ note: '', color })
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
        color: safeAnnColor(payload.color),
        sentence_idx: annSheet.sentenceIdx,
      })
      annSheet.open = false
      await refresh()
      return true
    } catch {
      return false
    }
  }

  /**
   * 编辑已有批注（修复「已批注句子颜色/内容都无法修改，只能删除」）：
   * 走既有 PATCH /api/v1/reading/annotations/{id}（后端 2026-09-10 已具备）；
   * 笔记清空 → kind 回落 highlight（与创建语义一致，避免「note 但没笔记」的脏数据）；
   * 颜色永远过白名单——后端 update 对空串不做 `or None` 处理，脏值会被原样存库。
   */
  async function update(id: number, payload: { note: string; color: string }): Promise<boolean> {
    const note = payload.note.trim()
    try {
      const updated = await patchAnnotation(id, {
        note,
        color: safeAnnColor(payload.color),
        kind: note ? 'note' : 'highlight',
      })
      await refresh()
      // 弹层里立即反映新值（用服务端返回为准，避免本地拼装与服务端不一致）
      noteSheet.item = annotations.value.find((a) => a.id === id) ?? updated
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
      sentList.open = false
      noteSheet.open = false
      noteSheet.item = null
    } catch {
      /* 非关键 */
    }
  }

  /** 列表点跳转：滚到该句 + 闪烁 + 直接弹出批注内容（修复前只滚动，看不到批注） */
  function jump(a: AnnotationItem): void {
    annListOpen.value = false
    sentList.open = false
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
    sentList,
    sentListItems,
    noteSheet,
    flashAnnId,
    refresh,
    annotationsOf,
    createFromSelection,
    createForSentence,
    chooseColorForSentence,
    highlightSentence,
    save,
    update,
    remove,
    jump,
    openNote,
    openNoteById,
    openSentence,
  }
}
