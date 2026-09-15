/**
 * 社区划词查义（社区 S3 · docs/47 §5.5 · 把读书域的查词能力接进社区）
 *
 * 复用读书域三件套：`useWordLookup`（查词状态）/ `MobileWordCard`（词卡展示层）/
 * `useWordAudio`（词音 blob 管道）；本模块只做社区特有的部分：
 *
 * 1. **选区 → 单词**：长按选中后取选区文本，剥首尾标点、只认单个英文词（多词/整句不弹卡）；
 * 2. **上下文句子**：从选区所在块（`[data-sentence]`）的 textContent 取整句，作为
 *    `context_snippet` 落库（生词本里能看到原句）；
 * 3. **来源标记**：`scene='community'`（后端 CHECK 已含该值，需接口入参支持 —— docs/48 B15）；
 * 4. **节流**：与阅读器同款 200ms 前沿节流（`selectionchange` 在拖动中高频触发）。
 *
 * 注意：阅读器的 200ms 节流服务的是**批注**，查词走点词；社区没有「点词」语义（整卡要能点进详情），
 * 所以社区划词走「长按选中 → 浮层」这一条路径（docs/48 §2 事实纠正）。
 */
import { ref } from 'vue'

import { useUiStore } from '@/stores/ui'
import { useWordAudio } from '@/composables/useWordAudio'
import { useWordLookup } from '@/composables/useWordLookup'

/** 选区文本 → 单个可查的英文词（含撇号/连字符）；多词或非英文 → null */
export function selectionToWord(raw: string): string | null {
  const text = raw.trim().replace(/^[^A-Za-z]+|[^A-Za-z'’-]+$/g, '')
  if (!text) return null
  if (!/^[A-Za-z][A-Za-z'’-]*$/.test(text)) return null
  if (text.length > 64) return null
  return text
}

export function useCommunityWordLookup() {
  const ui = useUiStore()
  const lookup = useWordLookup()
  const { play: playWordAudio } = useWordAudio()
  /** 划词浮层的提示（选区不是单词时给一句解释，而不是静默无反应） */
  const hint = ref('')
  let lastTs = 0

  /** selectionchange 处理器（绑在页面容器上；只处理容器内的选区） */
  function onSelectionChange(root: HTMLElement | null): void {
    if (!root) return
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) return
    if (!root.contains(sel.anchorNode ?? sel.focusNode)) return
    const now = Date.now()
    if (now - lastTs < 200) return
    lastTs = now

    const word = selectionToWord(sel.toString())
    if (!word) {
      hint.value = '划选一个英文单词即可查义'
      return
    }
    hint.value = ''
    void lookup.openFor(word, contextOf(sel, root), null)
  }

  /** 选区所在句：优先取带 data-sentence 的块，退化到最近块级元素 */
  function contextOf(sel: Selection, root: HTMLElement): string {
    const node = sel.anchorNode
    const el = (node?.nodeType === Node.TEXT_NODE ? node.parentElement : (node as HTMLElement)) ?? null
    const block =
      (el?.closest('[data-sentence]') as HTMLElement | null) ??
      (el?.closest('p, li, blockquote, div') as HTMLElement | null) ??
      root
    return block.textContent?.trim().slice(0, 500) ?? ''
  }

  /** 加入生词本（来源 community；社区帖无 book/chapter） */
  async function addToVocab(): Promise<void> {
    const ok = await lookup.addToVocab({ scene: 'community' })
    ui.showToast(ok ? '已加入生词本' : '加入失败')
  }

  /** 朗读该词 */
  async function playWord(): Promise<void> {
    const word = lookup.state.word
    if (!word) return
    const ok = await playWordAudio(word)
    if (!ok) ui.showToast('读音播放失败')
  }

  return { state: lookup.state, close: lookup.close, onSelectionChange, addToVocab, playWord, hint }
}
