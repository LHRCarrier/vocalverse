/**
 * 酒馆消息标注（本地标记；长按菜单「标注这条」）。
 *
 * 存储：localStorage 按剧本分键（`vv_trpg_marks_<campaignId>`），值为内容哈希数组——
 * 消息在服务端没有稳定 id 暴露给流式行（流内只有 turn_end 的 message_id），
 * 用内容哈希可同时覆盖「历史重建」与「流式新增」，且刷新后标记仍在。
 */
import { ref, type Ref } from 'vue'

function contentHash(text: string): string {
  let h = 5381
  for (let i = 0; i < text.length; i++) {
    h = ((h << 5) + h + text.charCodeAt(i)) | 0
  }
  return `${text.length}:${(h >>> 0).toString(36)}`
}

export function useTavernMarks() {
  const marks: Ref<Set<string>> = ref(new Set())
  let storageKey = 'vv_trpg_marks_0'

  function load(campaignId: number | null) {
    storageKey = `vv_trpg_marks_${campaignId ?? 0}`
    try {
      const raw = localStorage.getItem(storageKey)
      const parsed = raw ? (JSON.parse(raw) as string[]) : []
      marks.value = new Set(Array.isArray(parsed) ? parsed : [])
    } catch {
      marks.value = new Set()
    }
  }

  function has(content: string): boolean {
    return marks.value.has(contentHash(content))
  }

  function toggle(content: string): boolean {
    const key = contentHash(content)
    const next = new Set(marks.value)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    marks.value = next
    try {
      localStorage.setItem(storageKey, JSON.stringify([...next]))
    } catch {
      /* 隐私模式等不可写：仅本次会话有效 */
    }
    return next.has(key)
  }

  return { marks, load, has, toggle }
}

export type TavernMarks = ReturnType<typeof useTavernMarks>
