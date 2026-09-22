import { describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'

import type { TrpgEntityItem, TrpgState } from '@/api/trpg'
import { useTavernCast } from '@/composables/useTavernCast'

function entity(partial: Partial<TrpgEntityItem> & { name: string }): TrpgEntityItem {
  return { id: 1, kind: 'npc', status: 'active', pending: false, portrait: null, ...partial }
}

function makeState(entities: TrpgEntityItem[]): TrpgState {
  return {
    campaign: { id: 1, name: '迷雾酒馆', narrative_summary: '' },
    messages: [],
    facts: [],
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

describe('useTavernCast · 在场名单（entities + character 事件）', () => {
  it('三态划分：active 在场 / pending=arriving / cleared=departed；排序在场优先', () => {
    const state = ref(
      makeState([
        entity({ id: 1, name: '幽灵', status: 'cleared', pending: false }),
        entity({ id: 2, name: '莉亚', status: 'active', pending: false }),
        entity({ id: 3, name: '信使', status: 'active', pending: true }),
        entity({ id: 4, kind: 'pc', name: '主角', status: 'active', pending: false }),
      ]),
    )
    const cast = useTavernCast(state)
    expect(cast.members.value.map((m) => m.name)).toEqual(['莉亚', '主角', '信使', '幽灵'])
    expect(cast.present.value.map((m) => m.name)).toEqual(['莉亚', '主角'])
    expect(cast.arriving.value.map((m) => m.name)).toEqual(['信使'])
    expect(cast.departed.value.map((m) => m.name)).toEqual(['幽灵'])
    expect(cast.arriving.value[0]!.pending).toBe(true)
    expect(cast.arriving.value[0]!.status).toBe('arriving')
  })

  it('portraitFor 解析顺序：实体挂图 url → 内置素材（PC 占位/NPC 名字命中）→ null', () => {
    const state = ref(
      makeState([
        entity({
          id: 1,
          name: '莉亚',
          portrait: { media_id: 'm1', url: '/api/v1/media/m1' },
        }),
        entity({ id: 2, kind: 'pc', name: '主角' }),
        entity({ id: 3, name: '老陈' }),
        entity({ id: 4, name: '无名客' }),
      ]),
    )
    const cast = useTavernCast(state)
    expect(cast.portraitFor('莉亚')).toBe('/api/v1/media/m1')
    expect(cast.portraitFor('主角')).toContain('pc-avatar.webp')
    expect(cast.portraitFor('老陈')).toContain('npc-laochen.webp')
    expect(cast.portraitFor('无名客')).toBeNull()
    expect(cast.portraitFor('不存在')).toBeNull()
    // 成员对象直接携带解析后的立绘 URL（组件无需再探 art）
    expect(cast.members.value.find((m) => m.name === '莉亚')?.portraitUrl).toBe('/api/v1/media/m1')
  })

  it('character 事件：实体未落表也能出现在条上（arriving → active → departed）', async () => {
    const state = ref(makeState([entity({ id: 1, name: '莉亚' })]))
    const cast = useTavernCast(state)

    cast.apply({ type: 'character', name: '老陈', kind: 'npc', status: 'arriving', note: '从后厨赶来' })
    const arrival = cast.members.value.find((m) => m.name === '老陈')!
    expect(arrival.status).toBe('arriving')
    expect(arrival.note).toBe('从后厨赶来')
    expect(arrival.entityId).toBeNull()

    cast.apply({ type: 'character', name: '老陈', kind: 'npc', status: 'active' })
    expect(cast.present.value.some((m) => m.name === '老陈')).toBe(true)

    cast.apply({ type: 'character', name: '莉亚', kind: 'npc', status: 'departed', note: '离店' })
    expect(cast.departed.value.map((m) => m.name)).toContain('莉亚')

    // 状态刷新 → 事件增量清空，按快照回落
    state.value = makeState([entity({ id: 1, name: '莉亚' })])
    await nextTick()
    expect(cast.members.value.map((m) => m.name)).toEqual(['莉亚'])
  })

  it('空实体表 → 空名单（不炸）', () => {
    const cast = useTavernCast(ref(makeState([])))
    expect(cast.members.value).toEqual([])
    expect(cast.arriving.value).toEqual([])
  })
})
