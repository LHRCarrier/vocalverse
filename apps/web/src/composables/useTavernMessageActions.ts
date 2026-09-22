/**
 * 酒馆消息长按操作（视图编排薄层）：动作条开关 + 听这句 / 标注 / 复制 + 高亮判定。
 *
 * 抽出原因：MobileTavernView 已接近 fe-08 行数上限；且这段是纯视图逻辑（无 API）。
 */
import { computed, ref, type Ref } from 'vue'

import type { TavernAudio } from '@/composables/useTavernAudio'
import type { TavernMarks } from '@/composables/useTavernMarks'
import type { TavernRow } from '@/composables/useTavernSession'
import type { TavernTranslations } from '@/composables/useTavernTranslations'

export function useTavernMessageActions(
  rows: Ref<TavernRow[]>,
  audio: TavernAudio,
  marks: TavernMarks,
  translations: TavernTranslations,
) {
  /** 长按操作菜单对应的行下标（null = 未打开） */
  const actionIndex = ref<number | null>(null)
  const actionRow = computed(() =>
    actionIndex.value == null ? null : (rows.value[actionIndex.value] ?? null),
  )

  function open(index: number) {
    actionIndex.value = index
  }

  function listen() {
    const row = actionRow.value
    if (!row || row.kind === 'system' || !row.content.trim()) return
    const index = actionIndex.value!
    actionIndex.value = null
    void audio.replay(index, row.content)
  }

  /** 所选消息预览（首 48 字，换行折成空格） */
  const preview = computed(() => {
    const row = actionRow.value
    if (!row) return ''
    return row.content.replace(/\s+/g, ' ').trim().slice(0, 48)
  })

  /** 译文是否正在展示（菜单项文案「看原文」） */
  const translated = computed(() => {
    if (actionIndex.value == null) return false
    return translations.stateFor(actionIndex.value)?.showing === true
  })

  function translate() {
    const row = actionRow.value
    const index = actionIndex.value
    if (!row || index == null || !row.content.trim()) return
    actionIndex.value = null
    void translations.toggle(index, row.content)
  }

  function toggleMark() {
    const row = actionRow.value
    if (!row) return
    marks.toggle(row.content)
    actionIndex.value = null
  }

  async function copy() {
    const row = actionRow.value
    if (!row) return
    actionIndex.value = null
    try {
      await navigator.clipboard.writeText(row.content)
    } catch {
      /* 剪贴板不可用（http / 权限）：静默 */
    }
  }

  /** 该行当前是否处于朗读高亮 */
  function highlightFor(index: number) {
    const hl = audio.highlight.value
    return hl && hl.rowIndex === index ? hl : null
  }

  function close() {
    actionIndex.value = null
  }

  return {
    actionIndex,
    actionRow,
    preview,
    translated,
    open,
    listen,
    translate,
    toggleMark,
    copy,
    highlightFor,
    close,
  }
}

export type TavernMessageActions = ReturnType<typeof useTavernMessageActions>
