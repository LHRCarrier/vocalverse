/**
 * 阅读器 · 划词监听（2026-09-09 抽离，让 MobileReaderView 守住 fe-08 的 350 行门禁）。
 *
 * 语义：`selectionchange` 在拖动选词过程中高频触发 → 200ms 前沿节流；只处理**非折叠**选区，
 * 且选区必须落在正文容器内（顶栏/弹层里的选词不触发批注）。
 *
 * 与长按的关系：长按（静止）由 `useReaderTap` 判为「整句批注」并主动 `removeAllRanges()`，
 * 但 WebView 的原生选词可能在长按后 ~500ms 才出现 —— 因此调用方要传 `suppressed`，
 * 在长按窗口内忽略 selectionchange，避免先弹句子卡再弹划词卡。
 */
import { onBeforeUnmount, onMounted } from 'vue'

export interface ReaderSelectionDeps {
  /** 正文容器（选区必须在其中） */
  root: () => HTMLElement | null
  /** 命中有效选区（未折叠 + 在容器内 + 未被抑制） */
  onSelect: (selection: Selection) => void
  /** 返回 true = 当前应忽略选区（长按抑制窗口） */
  suppressed?: () => boolean
}

const THROTTLE_MS = 200

export function useReaderSelection(deps: ReaderSelectionDeps): void {
  let lastTs = 0

  function handler(): void {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) return
    if (deps.suppressed?.()) return
    const now = Date.now()
    if (now - lastTs < THROTTLE_MS) return
    lastTs = now
    if (deps.root()?.contains(sel.anchorNode ?? sel.focusNode)) deps.onSelect(sel)
  }

  onMounted(() => document.addEventListener('selectionchange', handler))
  onBeforeUnmount(() => document.removeEventListener('selectionchange', handler))
}
