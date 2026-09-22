/**
 * 酒馆 · 确定性结算编排（docs/57 §3.1/§3.2，从 useTavernSession 拆出以守 fe-08 行数）：
 *
 * - 结局行 upsert：实时 `ending` 事件与系统卡同任务只保留一张（前端去重）；
 * - `settle(quest)`：调 `POST /campaigns/{id}/quests/settle`（幂等）；成功消费返回结局 +
 *   置「已完结」；失败回退为文本行动（旧路径靠 DM 结算）。
 */
import { computed, ref, type Ref } from 'vue'

import { settleQuest as settleQuestApi, type TrpgState } from '@/api/trpg'
import type { TrpgEndingEvent } from '@/audio/trpg-sse-types'

import type { TavernRow } from './useTavernSession'

/** 结局系统行 upsert（同任务只保留一张；payload 字段与 `trpg_sys=ending` 系统卡同构） */
export function upsertEndingRow(rows: Ref<TavernRow[]>, payload: Record<string, unknown>): void {
  const quest = String(payload.quest ?? '')
  const index = rows.value.findIndex(
    (r) => r.payload?.trpg_sys === 'ending' && String(r.payload?.quest ?? '') === quest,
  )
  if (index >= 0) rows.value[index] = { ...rows.value[index]!, payload }
  else rows.value.push({ role: 'assistant', kind: 'system', content: '', payload })
}

export interface TavernSettleDeps {
  campaignId: Ref<number | null>
  rows: Ref<TavernRow[]>
  state: Ref<TrpgState | null>
  applyEnding: (ending: TrpgEndingEvent) => void
  /** 失败回退：发一条文本行动 */
  sendFallback: (text: string) => void
  refresh: () => Promise<void>
  setError: (message: string | null) => void
  /** 结算成功后的状态提示（statusHint） */
  onSettled: () => void
}

export function useTavernSettle(deps: TavernSettleDeps) {
  const settling = ref(false)
  /** 本地结算标记：settle 成功即置位（避免 refresh 竞态把「已完结」闪没） */
  const settledLocal = ref(false)
  const finished = computed(() => settledLocal.value || deps.state.value?.finished === true)

  function reset() {
    settledLocal.value = false
    settling.value = false
  }

  async function settle(quest: string, outcome?: 'strong' | 'weak' | 'miss'): Promise<boolean> {
    if (deps.campaignId.value == null || settling.value) return false
    settling.value = true
    deps.setError(null)
    try {
      const result = await settleQuestApi(deps.campaignId.value, quest, outcome)
      settledLocal.value = true
      deps.applyEnding({
        type: 'ending',
        quest: result.quest,
        outcome: result.outcome,
        title: result.title,
        text: result.text,
        epilogue: result.epilogue,
      })
      upsertEndingRow(deps.rows, {
        trpg_sys: 'ending',
        quest: result.quest,
        outcome: result.outcome,
        title: result.title,
        text: result.text,
        epilogue: result.epilogue,
      })
      if (deps.state.value) {
        deps.state.value = {
          ...deps.state.value,
          finished: result.finished,
          finished_at: new Date().toISOString(),
        }
      }
      deps.onSettled()
      void deps.refresh()
      return true
    } catch (e) {
      // 失败回退：先发文本行动（sendTurn 会清空 error），再置错误
      deps.sendFallback(`我想结算任务：${quest}`)
      deps.setError((e as Error).message)
      return false
    } finally {
      settling.value = false
    }
  }

  return { settling, finished, settle, reset }
}
