/**
 * 酒馆 · 遭遇 / 道具 / 动作面板数据（docs/56 §6：一域一 composable，不发请求）。
 *
 * 数据来源：
 * - 遭遇：事实 `encounter.{id}.status|order|turn|round`（order 为 JSON 数组字符串）+
 *   `encounter` SSE 事件增量；参战者 HP 取 `npc.{名}.hp` / `pc.{名}.hp`；
 * - 道具：事实 `item.{名}.qty|owner|effect|consumable`（docs/56 §2，owner 为 `pc.{名}`）。
 *
 * `item_used` 不是 SSE 事件（docs/56 §5）：道具数量变化靠回合结束的状态刷新回落。
 */
import { computed, ref, watch, type Ref } from 'vue'

import type { TrpgFactItem, TrpgState } from '@/api/trpg'
import type { TrpgEncounterEvent } from '@/audio/trpg-sse-types'

export type TavernParticipantKind = 'pc' | 'npc'

export interface TavernParticipant {
  /** 规范化键：`pc.主角` / `npc.地精` */
  key: string
  kind: TavernParticipantKind
  name: string
  hp: string | null
  /** 先攻序当前行动者（encounter.order[turn]） */
  current: boolean
}

export interface TavernEncounter {
  id: string
  status: 'active' | 'done'
  order: string[]
  turn: number
  round: number
  currentKey: string | null
  currentName: string | null
}

export interface TavernItem {
  name: string
  qty: number
  owner: string | null
  effect: string | null
  consumable: boolean
}

/** 建议行动（通用文本动作，经 session.sendText 走 DM 工具循环） */
export const TAVERN_SUGGESTIONS: ReadonlyArray<{ label: string; text: string }> = [
  { label: '观察', text: '我仔细观察四周' },
  { label: '交谈', text: '我试着与对方交谈' },
  { label: '前进', text: '我继续向前推进' },
]

const ENCOUNTER_KEY_RE = /^encounter\.(.+)\.(status|order|turn|round)$/
const ITEM_KEY_RE = /^item\.(.+)\.(qty|owner|effect|consumable)$/
const HP_KEY_RE = /^(npc|pc)\.(.+)\.hp$/

function intOrNull(value: string | null | undefined): number | null {
  const num = Number(String(value ?? '').trim())
  return Number.isInteger(num) ? num : null
}

/** 参战者键解析（`npc.地精` → kind/name）；非法 → null。 */
export function parseParticipantKey(key: string): { kind: TavernParticipantKind; name: string } | null {
  const raw = String(key ?? '').trim()
  const dot = raw.indexOf('.')
  if (dot <= 0) return null
  const kind = raw.slice(0, dot)
  const name = raw.slice(dot + 1).trim()
  if ((kind !== 'pc' && kind !== 'npc') || !name) return null
  return { kind, name }
}

/** 先攻序 JSON 字符串 → 列表；坏值宽容返回 []（刷新时不炸面板）。 */
export function decodeOrder(value: string | null | undefined): string[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

/** 事实表 → 遭遇（取进行中的一条；多条 active 取最后写入） */
function parseEncounters(facts: TrpgFactItem[]): Map<string, TavernEncounter> {
  const map = new Map<string, TavernEncounter>()
  for (const fact of facts) {
    const matched = ENCOUNTER_KEY_RE.exec(fact.key)
    if (!matched) continue
    const id = matched[1]!
    const prop = matched[2]!
    let current = map.get(id)
    if (!current) {
      current = { id, status: 'active', order: [], turn: 0, round: 1, currentKey: null, currentName: null }
      map.set(id, current)
    }
    if (prop === 'status') current.status = fact.value === 'done' ? 'done' : 'active'
    else if (prop === 'order') current.order = decodeOrder(fact.value)
    else if (prop === 'turn') current.turn = intOrNull(fact.value) ?? 0
    else current.round = intOrNull(fact.value) ?? 1
  }
  for (const current of map.values()) {
    current.currentKey = current.order[current.turn] ?? null
    const parsed = current.currentKey ? parseParticipantKey(current.currentKey) : null
    current.currentName = parsed?.name ?? null
  }
  return map
}

function activeOf(map: Map<string, TavernEncounter>): TavernEncounter | null {
  let found: TavernEncounter | null = null
  for (const encounter of map.values()) if (encounter.status === 'active') found = encounter
  return found
}

/** 事实表 → HP 映射（`npc.地精.hp` → `{ 'npc.地精': '7' }`） */
function parseHp(facts: TrpgFactItem[]): Map<string, string> {
  const map = new Map<string, string>()
  for (const fact of facts) {
    const matched = HP_KEY_RE.exec(fact.key)
    if (matched) map.set(`${matched[1]}.${matched[2]}`, fact.value)
  }
  return map
}

/** 事实表 → 道具条目（同名多属性合并；未知属性忽略） */
function parseItems(facts: TrpgFactItem[]): Map<string, TavernItem> {
  const map = new Map<string, TavernItem>()
  for (const fact of facts) {
    const matched = ITEM_KEY_RE.exec(fact.key)
    if (!matched) continue
    const name = matched[1]!
    const prop = matched[2]!
    let item = map.get(name)
    if (!item) {
      item = { name, qty: 0, owner: null, effect: null, consumable: true }
      map.set(name, item)
    }
    if (prop === 'qty') item.qty = intOrNull(fact.value) ?? 0
    else if (prop === 'owner') item.owner = fact.value || null
    else if (prop === 'effect') item.effect = fact.value || null
    else item.consumable = fact.value !== 'false'
  }
  return map
}

export function useTavernEncounter(state: Ref<TrpgState | null>) {
  const overlay = ref<Partial<TavernEncounter> | null>(null)
  const hpOverrides = ref(new Map<string, string>())

  watch(
    () => state.value,
    () => {
      overlay.value = null
      hpOverrides.value.clear()
    },
  )

  /** 玩家自身 PC 实体（攻击目标排除自己；单 PC 口径，多 PC 后续再议） */
  const self = computed(() => state.value?.entities.find((e) => e.kind === 'pc') ?? null)

  const encounter = computed<TavernEncounter | null>(() => {
    const base = activeOf(parseEncounters(state.value?.facts ?? []))
    if (!overlay.value) return base
    const merged: TavernEncounter = {
      id: overlay.value.id ?? base?.id ?? 'main',
      status: overlay.value.status ?? base?.status ?? 'active',
      order: overlay.value.order ?? base?.order ?? [],
      turn: overlay.value.turn ?? base?.turn ?? 0,
      round: overlay.value.round ?? base?.round ?? 1,
      currentKey: null,
      currentName: null,
    }
    merged.currentKey = merged.order[merged.turn] ?? null
    merged.currentName = merged.currentKey
      ? (parseParticipantKey(merged.currentKey)?.name ?? null)
      : null
    return merged.status === 'active' ? merged : null
  })

  /** 参战者（先攻序 + HP 覆盖 + 当前行动者标记） */
  const participants = computed<TavernParticipant[]>(() => {
    const current = encounter.value
    if (!current) return []
    const hpFacts = parseHp(state.value?.facts ?? [])
    return current.order.flatMap((key, index) => {
      const parsed = parseParticipantKey(key)
      if (!parsed) return []
      return [
        {
          key,
          kind: parsed.kind,
          name: parsed.name,
          hp: hpOverrides.value.get(key) ?? hpFacts.get(key) ?? null,
          current: index === current.turn,
        },
      ]
    })
  })

  /** 可攻击的在场目标（npc/pc 且未离场；排除玩家自身 PC） */
  const attackTargets = computed<TavernParticipant[]>(() => {
    const hpFacts = parseHp(state.value?.facts ?? [])
    const selfName = self.value?.name ?? null
    return (state.value?.entities ?? [])
      .filter((e) => (e.kind === 'npc' || e.kind === 'pc') && e.status !== 'cleared')
      .filter((e) => e.name !== selfName)
      .map((e) => ({
        key: `${e.kind}.${e.name}`,
        kind: e.kind === 'pc' ? ('pc' as const) : ('npc' as const),
        name: e.name,
        hp: hpFacts.get(`${e.kind}.${e.name}`) ?? null,
        current: false,
      }))
  })

  /** 持有者可用的道具（qty>0；owner 为 `pc.{自己}` 或无主时按玩家背包处理） */
  const items = computed<TavernItem[]>(() => {
    const ownerKey = self.value ? `pc.${self.value.name}` : null
    return [...parseItems(state.value?.facts ?? []).values()]
      .filter((item) => item.qty > 0)
      .filter((item) => !item.owner || (ownerKey ? item.owner === ownerKey : item.owner.startsWith('pc.')))
  })

  /** 应用 `encounter` 事件：四相增量（start/turn 覆盖序；attack 覆盖目标 HP；end 关闭） */
  function apply(e: TrpgEncounterEvent): void {
    const base = overlay.value ?? activeOf(parseEncounters(state.value?.facts ?? [])) ?? null
    const current: Partial<TavernEncounter> = { ...(base ?? { id: 'main', status: 'active' }) }
    if (e.kind === 'start' || e.kind === 'turn') {
      if (e.order) current.order = e.order
      if (e.turn != null) current.turn = e.turn
      if (e.round != null) current.round = e.round
      current.status = 'active'
    } else if (e.kind === 'attack') {
      if (e.target && e.target_hp != null) hpOverrides.value.set(e.target, String(e.target_hp))
      if (e.attacker && !current.order?.includes(e.attacker)) {
        current.order = [...(current.order ?? []), e.attacker]
      }
      if (e.target && !current.order?.includes(e.target)) {
        current.order = [...(current.order ?? []), e.target]
      }
    } else {
      current.status = 'done'
    }
    overlay.value = current
  }

  return { encounter, participants, attackTargets, items, suggestions: TAVERN_SUGGESTIONS, apply }
}
