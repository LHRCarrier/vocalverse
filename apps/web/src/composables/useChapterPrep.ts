/**
 * 阅读器 · 整章预合成状态（docs/45 §5.2）：SSE 进度 → 播放即 0 等待；复用 openSseFetch。
 */
import { reactive, ref } from 'vue'

import { prepareChapter } from '@/api/reading'

export function useChapterPrep() {
  const prepState = reactive({
    status: 'idle' as 'idle' | 'running' | 'done' | 'failed',
    done: 0,
    total: 0,
    text: '',
  })
  const prepAbort = ref<AbortController | null>(null)

  function start(chapterId: number, voice: string): void {
    prepState.status = 'running'
    prepState.done = 0
    prepState.text = '预合成中…'
    prepAbort.value?.abort()
    const ctrl = new AbortController()
    prepAbort.value = ctrl
    prepareChapter(
      chapterId,
      voice,
      {
        onEvent: (e) => {
          if (e.type === 'task_start') {
            prepState.total = e.total
          } else if (e.type === 'sentence_progress') {
            prepState.done = Math.max(prepState.done, e.done)
          } else if (e.type === 'task_done') {
            prepState.status = e.status === 'done' ? 'done' : 'failed'
            prepState.text = e.status === 'done' ? '已合成就绪 · 播放即 0 等待' : '部分失败，播放时补合成'
          } else if (e.type === 'error') {
            prepState.status = 'failed'
            prepState.text = e.message
          }
        },
        onError: () => {
          prepState.status = 'failed'
          prepState.text = '预合成未开启（引擎不可用）'
        },
      },
      ctrl.signal,
    )
  }

  return { prepState, start }
}
