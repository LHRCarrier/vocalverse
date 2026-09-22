/**
 * 酒馆 · 进度钟 / 结局（docs/56 §6：一域一 composable，规则派生不发请求）。
 *
 * 数据来源：
 * - 进度钟：`state.facts` 的 `quest.{名}.progress|kind|stage|status`（刷新恢复），
 *   叠加 `quest` SSE 事件增量（不必等回合结束的状态刷新即可看到推进）；
 * - 结局：`ending` SSE 事件（同回合展示）；后端另落系统卡 `trpg_sys="ending"`，
 *   刷新后由 `TrpgMessageItem` 走 `readEndingPayload` 渲染。
 */
import { computed, ref, watch, type Ref } from 'vue'

import type { TrpgFactItem, TrpgState } from '@/api/trpg'
import type { TrpgEndingEvent, TrpgQuestEvent } from '@/audio/trpg-sse-types'

export type TavernQuestKind = 'positive' | 'threat'
export type TavernEndingOutcome = 'strong' | 'weak' | 'miss'

export interface TavernQuest {
  name: string
  /** 显示串（`"3/6"`） */
  progress: string
  current: number
  segments: number
  kind: TavernQuestKind
  stage: string | null
  status: string
  full: boolean
  reason: string | null
  /** 是否为真正的进度钟（有 progress/kind 事实或收到过 quest 事件）；仅 status 的任务行不算 */
  hasClock: boolean
}

export interface TavernEnding {
  quest: string
  outcome: TavernEndingOutcome
  title: string
  text: string
  epilogue: string
}

/** 缺省总格数（与后端 progress.DEFAULT_SEGMENTS 对齐：BitD 常用 4/6/8 取中位数） */
const DEFAULT_SEGMENTS = 6
const QUEST_KEY_RE = /^quest\.(.+)\.(progress|kind|stage|status)$/
const OUTCOMES: readonly TavernEndingOutcome[] = ['strong', 'weak', 'miss']

/** 解析 `"3/6"` → `{current, segments}`；纯数字按缺省总格；非法 → null。 */
export function parseProgress(
  value: string | null | undefined,
): { current: number; segments: number } | null {
  const text = String(value ?? '').trim()
  if (!text) return null
  const [left, right] = text.includes('/') ? text.split('/', 2) : [text, String(DEFAULT_SEGMENTS)]
  const current = Number(left)
  const segments = Number(right)
  if (!Number.isFinite(current) || !Number.isFinite(segments)) return null
  if (current < 0 || segments <= 0) return null
  return { current, segments }
}

/**
 * 系统卡 payload → 结局（`trpg_sys="ending"` 的刷新渲染路径）。
 * 非 ending 卡 / 字段缺失或非法 → null（调用方降级为普通文本）。
 */
export function readEndingPayload(
  payload: Record<string, unknown> | null | undefined,
): TavernEnding | null {
  if (!payload || payload.trpg_sys !== 'ending') return null
  const outcome = String(payload.outcome ?? '') as TavernEndingOutcome
  const quest = String(payload.quest ?? '').trim()
  const title = String(payload.title ?? '').trim()
  if (!quest || !title || !OUTCOMES.includes(outcome)) return null
  return {
    quest,
    outcome,
    title,
    text: String(payload.text ?? ''),
    epilogue: String(payload.epilogue ?? ''),
  }
}

function blankQuest(name: string): TavernQuest {
  return {
    name,
    progress: `0/${DEFAULT_SEGMENTS}`,
    current: 0,
    segments: DEFAULT_SEGMENTS,
    kind: 'positive',
    stage: null,
    status: 'active',
    full: false,
    reason: null,
    hasClock: false,
  }
}

/** 事实表 → 进度钟映射（同名任务的多条事实合并；未知属性忽略）。 */
function parseQuestFacts(facts: TrpgFactItem[]): Map<string, TavernQuest> {
  const map = new Map<string, TavernQuest>()
  for (const fact of facts) {
    const matched = QUEST_KEY_RE.exec(fact.key)
    if (!matched) continue
    const name = matched[1]!
    const prop = matched[2]!
    let quest = map.get(name)
    if (!quest) {
      quest = blankQuest(name)
      map.set(name, quest)
    }
    if (prop === 'progress') {
      quest.progress = fact.value
      const parsed = parseProgress(fact.value)
      if (parsed) {
        quest.current = parsed.current
        quest.segments = parsed.segments
        quest.full = parsed.current >= parsed.segments
        quest.hasClock = true
      }
    } else if (prop === 'kind') {
      quest.kind = fact.value === 'threat' ? 'threat' : 'positive'
      quest.hasClock = true
    } else if (prop === 'stage') {
      quest.stage = fact.value || null
    } else {
      quest.status = fact.value || 'active'
    }
  }
  return map
}

/** 排序档：进行中的威胁钟最先（最紧迫），其次正向钟，再到已结算（done/failed 沉底）。 */
function questRank(quest: TavernQuest): number {
  if (quest.status !== 'active') return quest.status === 'done' ? 3 : 4
  return quest.kind === 'threat' ? 0 : 1
}

export function useTavernQuest(state: Ref<TrpgState | null>) {
  /** SSE 增量覆盖（回合内即时；状态快照刷新后以事实为准） */
  const overlays = ref(new Map<string, Partial<TavernQuest>>())
  const ending = ref<TavernEnding | null>(null)

  watch(
    () => state.value,
    () => overlays.value.clear(),
  )

  const quests = computed<TavernQuest[]>(() => {
    const merged = parseQuestFacts(state.value?.facts ?? [])
    for (const [name, patch] of overlays.value) {
      const base = merged.get(name) ?? blankQuest(name)
      merged.set(name, { ...base, ...patch, name })
    }
    return [...merged.values()].sort((a, b) => questRank(a) - questRank(b))
  })

  const activeQuests = computed(() => quests.value.filter((q) => q.status === 'active'))
  /** 任一进行中的进度钟已满（顶部条强调「可结算」） */
  const hasFullClock = computed(() => activeQuests.value.some((q) => q.full))

  /** 应用 `quest` 事件：按事件字段增量覆盖（事实表缺行时也能立即可见）。 */
  function apply(e: TrpgQuestEvent): void {
    const parsed = parseProgress(e.progress)
    const patch: Partial<TavernQuest> = {
      progress: e.progress,
      kind: e.kind === 'threat' ? 'threat' : 'positive',
      reason: e.reason ?? null,
      full: e.full,
      hasClock: true,
    }
    if (parsed) {
      patch.current = parsed.current
      patch.segments = parsed.segments
    } else {
      patch.segments = e.segments > 0 ? e.segments : DEFAULT_SEGMENTS
      patch.current = 0
    }
    if (e.segments > 0) patch.segments = e.segments
    overlays.value.set(e.quest, patch)
  }

  function applyEnding(e: TrpgEndingEvent): void {
    ending.value = {
      quest: e.quest,
      outcome: e.outcome,
      title: e.title,
      text: e.text,
      epilogue: e.epilogue,
    }
  }

  function clearEnding(): void {
    ending.value = null
  }

  return {
    quests,
    activeQuests,
    hasFullClock,
    ending,
    apply,
    applyEnding,
    clearEnding,
    readEndingPayload,
  }
}
