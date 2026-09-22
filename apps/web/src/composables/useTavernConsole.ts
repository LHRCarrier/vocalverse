/**
 * 酒馆主持台动作（用户权威路径）：事实手改/删除、任务线索增改、切场景、桌骰、摘要重渲染。
 *
 * 从 useTavernSession 拆出（fe-08 文件行数约束）：只依赖 campaignId / refresh / rows，
 * 不持有会话状态本身。
 */
import type { Ref } from 'vue'

import {
  createClue,
  createTask,
  deleteFact,
  editFact,
  refreshNarrative,
  rollDice,
  setClueRecovered,
  setScene,
  setTaskStatus,
} from '@/api/trpg'

import type { TavernRow } from './useTavernSession'

export interface TavernConsoleDeps {
  campaignId: Ref<number | null>
  rows: Ref<TavernRow[]>
  /** 当前场景（建任务/线索时带上场景过滤字段） */
  scene: () => string | null | undefined
  refresh: () => Promise<void>
  onError: (message: string) => void
}

export function useTavernConsole(deps: TavernConsoleDeps) {
  async function onEditFact(key: string, value: string) {
    if (deps.campaignId.value == null) return
    await editFact(deps.campaignId.value, key, value)
    await deps.refresh()
  }

  async function onDeleteFact(key: string) {
    if (deps.campaignId.value == null) return
    await deleteFact(deps.campaignId.value, key)
    await deps.refresh()
  }

  async function onCreateTask(title: string) {
    if (deps.campaignId.value == null) return
    await createTask(deps.campaignId.value, title, deps.scene() ?? undefined)
    await deps.refresh()
  }

  async function onSetTaskStatus(taskId: number, taskStatus: string) {
    if (deps.campaignId.value == null) return
    await setTaskStatus(deps.campaignId.value, taskId, taskStatus)
    await deps.refresh()
  }

  async function onCreateClue(title: string) {
    if (deps.campaignId.value == null) return
    await createClue(deps.campaignId.value, title, undefined, deps.scene() ?? undefined)
    await deps.refresh()
  }

  async function onRecoverClue(clueId: number, recovered: boolean) {
    if (deps.campaignId.value == null) return
    await setClueRecovered(deps.campaignId.value, clueId, recovered)
    await deps.refresh()
  }

  async function onSetScene(scene: string) {
    if (deps.campaignId.value == null) return
    await setScene(deps.campaignId.value, scene)
    await deps.refresh()
  }

  async function onRoll(payload: {
    dice: string
    modifier?: number
    vs?: number
    effectsText?: string
  }) {
    if (deps.campaignId.value == null) return
    try {
      const result = await rollDice(deps.campaignId.value, {
        dice: payload.dice,
        modifier: payload.modifier,
        vs: payload.vs,
        effects: parseEffects(payload.effectsText ?? ''),
      })
      deps.rows.value.push({
        role: 'assistant',
        kind: 'system',
        content: '',
        payload: { trpg_sys: 'dice', text: result.summary },
      })
      await deps.refresh()
    } catch (e) {
      deps.onError((e as Error).message)
    }
  }

  async function onRefreshNarrative() {
    if (deps.campaignId.value == null) return
    await refreshNarrative(deps.campaignId.value)
    await deps.refresh()
  }

  return {
    onEditFact,
    onDeleteFact,
    onCreateTask,
    onSetTaskStatus,
    onCreateClue,
    onRecoverClue,
    onSetScene,
    onRoll,
    onRefreshNarrative,
  }
}

/** 效果串解析：`pc.主角.hp:-5;scene.current:1` → [{key,delta}]；非法返回 undefined（后端拒绝） */
export function parseEffects(text: string): Array<{ key: string; delta: number }> | undefined {
  const items = text
    .split(/[;；]/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (!items.length) return undefined
  const out: Array<{ key: string; delta: number }> = []
  for (const item of items) {
    const idx = item.lastIndexOf(':')
    if (idx <= 0) return undefined
    const key = item.slice(0, idx).trim()
    const delta = Number(item.slice(idx + 1).trim())
    if (!key || !Number.isFinite(delta)) return undefined
    out.push({ key, delta })
  }
  return out
}
