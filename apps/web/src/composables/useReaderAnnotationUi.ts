/**
 * 阅读器 · 批注视图装配（2026-09-09）：把「批注状态 + 句尾编号标签渲染数据 + 带 toast 的动作」收进
 * 一个 composable，让 MobileReaderView 保持在 fe-08 的 350 行门禁内（新代码不豁免）。
 *
 * 分工：
 *   · useReaderAnnotations —— 纯状态与接口调用（无 UI 依赖，可单测）；
 *   · 本模块 —— 视图侧派生（句 → 批注映射）与用户反馈（toast）；
 *   · 视图 —— 只负责模板与点击/长按分发（useReaderTap）。
 */
import { computed, ref } from 'vue'

import { useReaderAnnotations } from '@/composables/useReaderAnnotations'
import { useUiStore } from '@/stores/ui'

import type { AnnotationItem, ReadingChapter } from '@/api/reading'

export function useReaderAnnotationUi(
  chapterId: number,
  getChapter: () => ReadingChapter | null,
  onJump: (sentenceIdx: number) => void,
) {
  const ui = useUiStore()
  const api = useReaderAnnotations(chapterId, getChapter, onJump)
  /** 单条批注保存中（PATCH 在飞）——由父级持有，失败后按钮自动恢复可点 */
  const noteBusy = ref(false)

  /** 句 → 该句批注（句尾编号标签渲染用；按起点排序 = 标签序号；批注变化时重算） */
  const annBySentence = computed<Map<number, AnnotationItem[]>>(() => {
    const map = new Map<number, AnnotationItem[]>()
    const ch = getChapter()
    if (!ch) return map
    for (const s of ch.sentences) {
      const list = api.annotations.value
        .filter((a) => a.start_offset < s.end && a.end_offset > s.start)
        .sort((x, y) => x.start_offset - y.start_offset)
      if (list.length) map.set(s.idx, list)
    }
    return map
  })

  async function saveAnnotation(payload: { note: string; color: string }) {
    const ok = await api.save(payload)
    ui.showToast(ok ? (api.annSheet.mode === 'highlight' ? '已高亮这句' : '已添加批注') : '保存失败')
  }

  /** 编辑已批注句子（改色/改笔记）——修复「只能删除」 */
  async function updateAnnotation(payload: { id: number; note: string; color: string }) {
    if (noteBusy.value) return
    noteBusy.value = true
    try {
      const ok = await api.update(payload.id, { note: payload.note, color: payload.color })
      ui.showToast(ok ? '已保存修改' : '保存失败，可重试')
    } finally {
      noteBusy.value = false
    }
  }

  async function removeAnnotation(id: number) {
    await api.remove(id)
    ui.showToast('已删除批注')
  }

  return {
    ...api,
    annBySentence,
    noteBusy,
    saveAnnotation,
    updateAnnotation,
    removeAnnotation,
  }
}
