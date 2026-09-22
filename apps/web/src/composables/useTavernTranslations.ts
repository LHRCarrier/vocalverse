/**
 * 酒馆消息翻译状态（X 式「翻译」按钮：点击翻译，再点显示原文）。
 *
 * 状态按「行下标」挂载（与消息流一致）；切剧本/重开时清空。
 * 方向由服务端按内容自动判定（中英互切），前端只负责展示与切换。
 */
import { computed, ref } from 'vue'

import { translateMessage } from '@/api/trpg'

export interface TranslationState {
  status: 'loading' | 'done' | 'error'
  text: string
  /** true = 当前展示译文；false = 展示原文 */
  showing: boolean
  target: 'zh' | 'en' | null
}

export function useTavernTranslations() {
  const states = ref<Record<number, TranslationState>>({})

  const map = computed(() => states.value)

  function stateFor(index: number): TranslationState | null {
    return map.value[index] ?? null
  }

  /** 点击「翻译/原文」：已翻译 → 切换展示；未翻译 → 调接口后展示 */
  async function toggle(index: number, content: string) {
    const current = stateFor(index)
    if (current?.status === 'done' && current.text) {
      states.value = { ...states.value, [index]: { ...current, showing: !current.showing } }
      return
    }
    states.value = {
      ...states.value,
      [index]: { status: 'loading', text: '', showing: false, target: null },
    }
    try {
      const result = await translateMessage(content)
      states.value = {
        ...states.value,
        [index]: {
          status: 'done',
          text: result.text,
          showing: true,
          target: result.target,
        },
      }
    } catch {
      states.value = { ...states.value, [index]: { status: 'error', text: '', showing: false, target: null } }
    }
  }

  function clear() {
    states.value = {}
  }

  return { states, stateFor, toggle, clear }
}

export type TavernTranslations = ReturnType<typeof useTavernTranslations>
