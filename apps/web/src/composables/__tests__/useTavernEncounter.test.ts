import { describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'

import type { TrpgEntityItem, TrpgFactItem, TrpgState } from '@/api/trpg'
import {
  decodeOrder,
  isInternalEntityName,
  isWeapon,
  parseParticipantKey,
  splitInventory,
  useTavernEncounter,
} from '@/composables/useTavernEncounter'

let factId = 0
function fact(key: string, value: string): TrpgFactItem {
  factId += 1
  return {
    id: factId,
    key,
    value,
    kind: 'state',
    modality: 'fact',
    speaker: null,
    importance: 0.5,
    user_touched_at: null,
    user_deleted_at: null,
  }
}

function entity(partial: Partial<TrpgEntityItem> & { name: string }): TrpgEntityItem {
  return { id: 1, kind: 'npc', status: 'active', pending: false, portrait: null, ...partial }
}

function makeState(facts: TrpgFactItem[], entities: TrpgEntityItem[] = []): TrpgState {
  return {
    campaign: { id: 1, name: '迷雾酒馆', narrative_summary: '' },
    messages: [],
    facts,
    tasks: [],
    clues: [],
    entities,
    events: [],
    scene: '酒馆',
    snapshot: '',
    narrative_summary: '',
    verify: { dangling: [], gap: false, missing: [], patch_text: null, contradiction: false },
  }
}

const ENCOUNTER_FACTS = [
  fact('encounter.main.status', 'active'),
  fact('encounter.main.order', '["pc.主角","npc.地精","npc.莉亚"]'),
  fact('encounter.main.turn', '1'),
  fact('encounter.main.round', '2'),
  fact('npc.地精.hp', '7'),
  fact('pc.主角.hp', '10'),
  fact('item.治疗药水.qty', '2'),
  fact('item.治疗药水.owner', 'pc.主角'),
  fact('item.治疗药水.effect', '回复5'),
  fact('item.治疗药水.consumable', 'true'),
  fact('item.毒刃.qty', '0'),
  fact('item.毒刃.owner', 'pc.主角'),
  fact('item.黑市货.qty', '1'),
  fact('item.黑市货.owner', 'npc.地精'),
]

const ENTITIES = [
  entity({ id: 1, kind: 'pc', name: '主角' }),
  entity({ id: 2, name: '地精' }),
  entity({ id: 3, name: '莉亚' }),
  entity({ id: 4, name: '幽灵', status: 'cleared' }),
]

describe('useTavernEncounter · 遭遇（facts + encounter 事件）', () => {
  it('解析 encounter facts：id/序/回合/轮次/当前行动者；参战者 HP 映射', () => {
    const encounter = useTavernEncounter(ref(makeState(ENCOUNTER_FACTS, ENTITIES)))
    const current = encounter.encounter.value!
    expect(current.id).toBe('main')
    expect(current.status).toBe('active')
    expect(current.order).toEqual(['pc.主角', 'npc.地精', 'npc.莉亚'])
    expect(current.turn).toBe(1)
    expect(current.round).toBe(2)
    expect(current.currentName).toBe('地精')

    const parts = encounter.participants.value
    expect(parts.map((p) => p.name)).toEqual(['主角', '地精', '莉亚'])
    expect(parts.map((p) => p.current)).toEqual([false, true, false])
    expect(parts[1]!.hp).toBe('7')
    expect(parts[2]!.hp).toBeNull()
  })

  it('attackTargets：只列在场 NPC（排除自己/已离场）；items：仅自己持有且 qty>0', () => {
    const encounter = useTavernEncounter(ref(makeState(ENCOUNTER_FACTS, ENTITIES)))
    expect(encounter.attackTargets.value.map((t) => t.name)).toEqual(['地精', '莉亚'])
    expect(encounter.attackTargets.value[0]!.hp).toBe('7')
    expect(encounter.attackTargets.value.every((t) => t.kind === 'npc')).toBe(true)
    expect(encounter.items.value.map((i) => i.name)).toEqual(['治疗药水'])
    expect(encounter.items.value[0]!.qty).toBe(2)
  })

  it('attackTargets 目标过滤（docs/57 P1-5）：内部名 main、同行 PC、赶来中与已离场都不出', () => {
    const encounter = useTavernEncounter(
      ref(
        makeState([], [
          entity({ id: 1, kind: 'pc', name: '主角' }),
          entity({ id: 2, name: '地精' }),
          entity({ id: 3, name: 'main' }),
          entity({ id: 4, kind: 'pc', name: '洛可' }),
          entity({ id: 5, name: '迟到者', pending: true }),
          entity({ id: 6, name: '幽灵', status: 'cleared' }),
        ]),
      ),
    )
    expect(encounter.attackTargets.value.map((t) => t.name)).toEqual(['地精'])
    expect(isInternalEntityName('main')).toBe(true)
    expect(isInternalEntityName('MAIN')).toBe(true)
    expect(isInternalEntityName('地精')).toBe(false)
  })

  it('行囊字符串兜底：只有 `pc.*.inventory`（没有 item.* 事实）也能出道具 chip', () => {
    const state = ref(
      makeState([fact('pc.主角.inventory', '短剑, 黄铜钥匙、治疗药水')], [ENTITIES[0]!]),
    )
    const encounter = useTavernEncounter(state)
    expect(encounter.items.value.map((i) => i.name)).toEqual(['短剑', '黄铜钥匙', '治疗药水'])
    expect(encounter.items.value.every((i) => i.qty === 1)).toBe(true)
    // 与 item.* 事实同名时不重复出 chip（事实优先）
    state.value = makeState(
      [fact('pc.主角.inventory', '短剑, 黄铜钥匙'), fact('item.短剑.qty', '1'), fact('item.短剑.owner', 'pc.主角')],
      [ENTITIES[0]!],
    )
    expect(encounter.items.value.map((i) => i.name)).toEqual(['短剑', '黄铜钥匙'])
  })

  it('武器候选：排除消耗品与治疗类效果（药水不能当武器）', () => {
    expect(splitInventory('短剑, 黄铜钥匙、治疗药水')).toEqual(['短剑', '黄铜钥匙', '治疗药水'])
    expect(splitInventory(null)).toEqual([])
    expect(isWeapon({ name: '短剑', qty: 1, owner: null, effect: null, consumable: false })).toBe(true)
    expect(isWeapon({ name: '治疗药水', qty: 2, owner: null, effect: '回复5', consumable: true })).toBe(false)
    // 未标 consumable=false 的默认消耗品不做武器
    expect(isWeapon({ name: '火把', qty: 1, owner: null, effect: null, consumable: true })).toBe(false)
    // 即便标记非消耗品，治疗类效果也排除
    expect(isWeapon({ name: '圣水', qty: 1, owner: null, effect: '恢复生命', consumable: false })).toBe(false)
  })

  it('encounter 事件：start 建序 → attack 覆盖目标 HP → turn 轮转 → end 关闭', async () => {
    const state = ref(makeState([], ENTITIES))
    const encounter = useTavernEncounter(state)

    encounter.apply({
      type: 'encounter',
      kind: 'start',
      order: ['npc.地精', 'pc.主角'],
      turn: 0,
      round: 1,
    })
    expect(encounter.encounter.value?.currentName).toBe('地精')
    expect(encounter.participants.value[0]!.hp).toBeNull()

    encounter.apply({
      type: 'encounter',
      kind: 'attack',
      attacker: 'pc.主角',
      target: 'npc.地精',
      hit: true,
      damage: 5,
      target_hp: 4,
    })
    expect(encounter.participants.value[0]!.hp).toBe('4')

    encounter.apply({
      type: 'encounter',
      kind: 'turn',
      order: ['npc.地精', 'pc.主角'],
      turn: 1,
      round: 2,
    })
    expect(encounter.encounter.value?.round).toBe(2)
    expect(encounter.encounter.value?.currentName).toBe('主角')

    encounter.apply({ type: 'encounter', kind: 'end', outcome: '击退' })
    expect(encounter.encounter.value).toBeNull()
    expect(encounter.participants.value).toEqual([])

    // 状态刷新 → 事件增量清空
    await nextTick()
    expect(encounter.encounter.value).toBeNull()
  })

  it('attack 事件可补建事实表尚无的参战者（order 追加）', () => {
    const encounter = useTavernEncounter(ref(makeState([], ENTITIES)))
    encounter.apply({
      type: 'encounter',
      kind: 'attack',
      attacker: 'pc.主角',
      target: 'npc.莉亚',
      hit: true,
      damage: 3,
      target_hp: 6,
    })
    expect(encounter.encounter.value?.order).toEqual(['pc.主角', 'npc.莉亚'])
    expect(encounter.participants.value.find((p) => p.name === '莉亚')?.hp).toBe('6')
  })

  it('空事实/坏 order：宽容降级（无遭遇、无参战者、不抛异常）', () => {
    const empty = useTavernEncounter(ref(makeState([])))
    expect(empty.encounter.value).toBeNull()
    expect(empty.participants.value).toEqual([])
    expect(empty.items.value).toEqual([])

    const broken = useTavernEncounter(
      ref(makeState([fact('encounter.main.order', 'not-json'), fact('encounter.main.status', 'active')])),
    )
    expect(broken.encounter.value?.order).toEqual([])
    expect(broken.encounter.value?.currentName).toBeNull()
  })

  it('decodeOrder / parseParticipantKey：非法输入返回空值', () => {
    expect(decodeOrder('["npc.地精", 3, "pc.主角"]')).toEqual(['npc.地精', 'pc.主角'])
    expect(decodeOrder(null)).toEqual([])
    expect(decodeOrder('{')).toEqual([])
    expect(parseParticipantKey('npc.地精')).toEqual({ kind: 'npc', name: '地精' })
    expect(parseParticipantKey('boss')).toBeNull()
    expect(parseParticipantKey('npc.')).toBeNull()
  })
})
