import { describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'

import type { TrpgFactItem, TrpgState } from '@/api/trpg'
import {
  parseProgress,
  readEndingPayload,
  useTavernQuest,
} from '@/composables/useTavernQuest'

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

function makeState(facts: TrpgFactItem[]): TrpgState {
  return {
    campaign: { id: 1, name: '迷雾酒馆', narrative_summary: '' },
    messages: [],
    facts,
    tasks: [],
    clues: [],
    entities: [],
    events: [],
    scene: '酒馆',
    snapshot: '',
    narrative_summary: '',
    verify: { dangling: [], gap: false, missing: [], patch_text: null, contradiction: false },
  }
}

describe('useTavernQuest · 进度钟（facts 解析 + quest 事件）', () => {
  it('解析 quest.* 事实：字段合并、威胁钟排最前、已结算沉底', () => {
    const state = ref(
      makeState([
        fact('quest.寻找戒指.progress', '3/6'),
        fact('quest.寻找戒指.kind', 'positive'),
        fact('quest.寻找戒指.stage', '调查'),
        fact('quest.寻找戒指.status', 'active'),
        fact('quest.阴影逼近.progress', '1/4'),
        fact('quest.阴影逼近.kind', 'threat'),
        fact('quest.旧案.status', 'done'),
      ]),
    )
    const quest = useTavernQuest(state)
    const list = quest.quests.value
    expect(list.map((q) => q.name)).toEqual(['阴影逼近', '寻找戒指', '旧案'])

    const ring = list[1]!
    expect(ring.current).toBe(3)
    expect(ring.segments).toBe(6)
    expect(ring.progress).toBe('3/6')
    expect(ring.stage).toBe('调查')
    expect(ring.status).toBe('active')
    expect(ring.full).toBe(false)
    expect(ring.hasClock).toBe(true)

    const threat = list[0]!
    expect(threat.kind).toBe('threat')
    expect(threat.hasClock).toBe(true)

    const legacy = list[2]!
    expect(legacy.hasClock).toBe(false)
    expect(legacy.status).toBe('done')
  })

  it('满格标记 + hasFullClock；空事实不炸（无任务 → 空列表）', () => {
    const empty = useTavernQuest(ref(makeState([])))
    expect(empty.quests.value).toEqual([])
    expect(empty.hasFullClock.value).toBe(false)

    const state = ref(
      makeState([fact('quest.终局.progress', '6/6'), fact('quest.终局.kind', 'positive')]),
    )
    const quest = useTavernQuest(state)
    expect(quest.quests.value[0]!.full).toBe(true)
    expect(quest.hasFullClock.value).toBe(true)
    expect(quest.activeQuests.value).toHaveLength(1)
  })

  it('quest 事件增量覆盖事实（无需等状态刷新）；状态刷新后以事实为准', async () => {
    const state = ref(makeState([fact('quest.寻找戒指.progress', '2/6')]))
    const quest = useTavernQuest(state)

    quest.apply({
      type: 'quest',
      quest: '寻找戒指',
      progress: '5/6',
      segments: 6,
      kind: 'positive',
      reason: '线索到手',
      full: false,
    })
    const updated = quest.quests.value[0]!
    expect(updated.progress).toBe('5/6')
    expect(updated.current).toBe(5)
    expect(updated.reason).toBe('线索到手')
    expect(updated.full).toBe(false)

    // 满格事件 → 强调
    quest.apply({
      type: 'quest',
      quest: '寻找戒指',
      progress: '6/6',
      segments: 6,
      kind: 'positive',
      full: true,
    })
    expect(quest.hasFullClock.value).toBe(true)

    // 状态刷新（快照换对象）→ 增量清空，回落事实值
    state.value = makeState([fact('quest.寻找戒指.progress', '2/6')])
    await nextTick()
    expect(quest.quests.value[0]!.progress).toBe('2/6')
    expect(quest.quests.value[0]!.full).toBe(false)
  })

  it('quest 事件可创建事实表尚无的钟（威胁钟颜色/进度按事件）', () => {
    const quest = useTavernQuest(ref(makeState([])))
    quest.apply({
      type: 'quest',
      quest: '阴影逼近',
      progress: '2/4',
      segments: 4,
      kind: 'threat',
      reason: null,
      full: false,
    })
    const created = quest.quests.value[0]!
    expect(created.kind).toBe('threat')
    expect(created.current).toBe(2)
    expect(created.segments).toBe(4)
    expect(created.hasClock).toBe(true)
  })

  it('ending 事件 + clearEnding', () => {
    const quest = useTavernQuest(ref(makeState([])))
    expect(quest.ending.value).toBeNull()
    quest.applyEnding({
      type: 'ending',
      quest: '寻找戒指',
      outcome: 'strong',
      title: '圆满结局 · 寻找戒指',
      text: '你做到了。',
      epilogue: '多年以后。',
    })
    expect(quest.ending.value?.outcome).toBe('strong')
    expect(quest.ending.value?.title).toContain('圆满结局')
    quest.clearEnding()
    expect(quest.ending.value).toBeNull()
  })

  it('parseProgress：分数/纯数字/非法输入', () => {
    expect(parseProgress('3/6')).toEqual({ current: 3, segments: 6 })
    expect(parseProgress('5')).toEqual({ current: 5, segments: 6 })
    expect(parseProgress('')).toBeNull()
    expect(parseProgress('abc')).toBeNull()
    expect(parseProgress('3/0')).toBeNull()
    expect(parseProgress('-1/6')).toBeNull()
  })

  it('readEndingPayload：系统卡 payload → 结局（非 ending / 缺字段 / 非法档位 → null）', () => {
    const payload = {
      trpg_sys: 'ending',
      quest: '寻找戒指',
      outcome: 'weak',
      title: '尘埃落定 · 寻找戒指',
      text: '代价与收获并存。',
      epilogue: '账留给下次相遇。',
    }
    expect(readEndingPayload(payload)?.outcome).toBe('weak')
    expect(readEndingPayload(null)).toBeNull()
    expect(readEndingPayload({ ...payload, trpg_sys: 'dice' })).toBeNull()
    expect(readEndingPayload({ ...payload, outcome: 'unknown' })).toBeNull()
    expect(readEndingPayload({ ...payload, title: '' })).toBeNull()
  })
})
