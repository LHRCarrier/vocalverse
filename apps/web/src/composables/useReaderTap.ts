/**
 * 阅读器正文点击/长按语义（2026-09-10 组长拍板 · 2026-09-09 增长按）：
 *   单击词   → 查词卡（释义 + 加入生词本）
 *   单击句子 → 选中该句（再点取消），底部动作条决定「高亮 / 批注 / 听这句」
 *   长按句子 → 直接打开该句的批注卡（静止 550ms；拖动则让位给原生划词）
 *   长按划选 → 仍走 selectionchange 的自由区间批注（高级用法，保留）
 *   听书进行中单击句子 → 从该句续播（保持原行为）
 *
 * 长按与划词的分工（关键）：WebView 长按默认会开始选词，两者必须互斥——
 * 静止 550ms 内位移 ≤8px 判为「长按句子」；一旦拖动即取消长按，交给原生选词
 * （视图层再用 suppressSelectionUntil 忽略长按窗口内的 selectionchange，避免双开弹层）。
 *
 * 抽到 composable 的原因：MobileReaderView 有 350 行门禁（fe-08），点击分发占 40+ 行。
 */
import { onBeforeUnmount, ref } from 'vue'

import type { AnnotationItem, ReadingSentence } from '@/api/reading'

const LONG_PRESS_MS = 550
const MOVE_TOLERANCE = 8
/** 长按触发后，多少毫秒内的 click 视为同一次长按（吞掉，避免再走「选中句子」） */
const CLICK_SWALLOW_MS = 700

export interface ReaderTapDeps {
  getSentence: (idx: number) => ReadingSentence | undefined
  /** 打开查词卡（带上该词所在句子 idx，供卡片里的「高亮这句/批注这句」） */
  openWord: (word: string, contextSentence: string, sentenceIdx: number | null) => void
  /** 按批注 id 打开批注查看弹层 */
  openNoteById: (id: number) => void
  /** 当前批注列表（取被点段落的批注用） */
  annotations: { value: AnnotationItem[] }
  ttsState: { value: string }
  ttsCurrentIdx: { value: number }
  playFrom: (idx: number) => void
  /** 长按句子 → 打开该句批注卡 */
  onLongPress?: (idx: number) => void
}

export function useReaderTap(deps: ReaderTapDeps) {
  /** 当前选中的句子 idx（null = 未选中） */
  const selIdx = ref<number | null>(null)

  let pressTimer: ReturnType<typeof setTimeout> | null = null
  let swallowUntil = 0
  let startX = 0
  let startY = 0

  function cancelPress(): void {
    if (pressTimer) {
      clearTimeout(pressTimer)
      pressTimer = null
    }
  }

  /** 长按计时开始（仅句子区、且非句尾编号标签） */
  function onPointerDown(e: PointerEvent): void {
    if (!deps.onLongPress) return
    const target = e.target as HTMLElement
    if (target.closest('.u-rd__senttag')) return // 编号标签是点按入口，不长按
    const sentenceEl = target.closest('.u-rd__sentence') as HTMLElement | null
    if (!sentenceEl) return
    const idx = Number(sentenceEl.dataset.idx ?? -1)
    if (idx < 0) return
    startX = e.clientX
    startY = e.clientY
    cancelPress()
    pressTimer = setTimeout(() => {
      pressTimer = null
      swallowUntil = Date.now() + CLICK_SWALLOW_MS
      // 掐掉原生选词（长按默认会选中一个词）——否则会先弹句子卡、再弹划词卡
      window.getSelection()?.removeAllRanges()
      deps.onLongPress?.(idx)
    }, LONG_PRESS_MS)
  }

  /** 一旦拖动就取消长按（让位给原生划词选择） */
  function onPointerMove(e: PointerEvent): void {
    if (!pressTimer) return
    if (
      Math.abs(e.clientX - startX) > MOVE_TOLERANCE ||
      Math.abs(e.clientY - startY) > MOVE_TOLERANCE
    ) {
      cancelPress()
    }
  }

  function onPointerUp(): void {
    cancelPress()
  }

  onBeforeUnmount(cancelPress)

  function clearSelection(): void {
    selIdx.value = null
  }

  function onReaderClick(e: MouseEvent): void {
    // 长按刚触发：吞掉这一次 click（否则会同时选中句子）
    if (Date.now() < swallowUntil) {
      swallowUntil = 0
      return
    }
    const target = e.target as HTMLElement

    // ① 句尾编号标签 → 看/改该条批注（优先于查词）
    const tagEl = target.closest('.u-rd__senttag') as HTMLElement | null
    if (tagEl?.dataset.ann) {
      clearSelection()
      deps.openNoteById(Number(tagEl.dataset.ann))
      return
    }

    const segEl = target.closest('.u-rd__seg') as HTMLElement | null
    const sentenceEl = target.closest('.u-rd__sentence') as HTMLElement | null

    // ② 词段 → 查词卡（任何词都可查）
    const word = segEl?.dataset.word ?? ''
    if (word) {
      clearSelection()
      const idx = Number(sentenceEl?.dataset.idx ?? -1)
      deps.openWord(word, idx >= 0 ? (deps.getSentence(idx)?.text ?? '') : '', idx >= 0 ? idx : null)
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

  return { selIdx, clearSelection, onReaderClick, onPointerDown, onPointerMove, onPointerUp }
}
