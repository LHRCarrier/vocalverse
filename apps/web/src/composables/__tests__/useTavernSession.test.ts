import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import type { TrpgEntityItem, TrpgFactItem, TrpgState } from '@/api/trpg'
import type { TavernAudio } from '@/composables/useTavernAudio'
import { useTavernSession } from '@/composables/useTavernSession'

const mocks = vi.hoisted(() => ({
  fetchCampaigns: {} as ReturnType<typeof vi.fn>,
  fetchCampaignState: {} as ReturnType<typeof vi.fn>,
  settleQuest: {} as ReturnType<typeof vi.fn>,
  streamTrpgTurn: {} as ReturnType<typeof vi.fn>,
}))

vi.mock('@/api/trpg', () => {
  mocks.fetchCampaigns = vi.fn()
  mocks.fetchCampaignState = vi.fn()
  mocks.settleQuest = vi.fn()
  mocks.streamTrpgTurn = vi.fn()
  return {
    fetchCampaigns: mocks.fetchCampaigns,
    fetchCampaignState: mocks.fetchCampaignState,
    settleQuest: mocks.settleQuest,
    streamTrpgTurn: mocks.streamTrpgTurn,
    createCampaign: vi.fn(),
    setScene: vi.fn(),
    editFact: vi.fn(),
    deleteFact: vi.fn(),
    restoreFact: vi.fn(),
    createTask: vi.fn(),
    setTaskStatus: vi.fn(),
    createClue: vi.fn(),
    setClueRecovered: vi.fn(),
    rollDice: vi.fn(),
    refreshNarrative: vi.fn(),
    clearCampaignMessages: vi.fn(),
  }
})

vi.mock('@/audio/recorder', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/audio/recorder')>()
  class FakeRecorder {
    state = 'idle'
    onStateChange: ((s: string) => void) | null = null
    onStop: (() => unknown) | null = null
    start = vi.fn(async () => undefined)
    stop = vi.fn()
    cancel = vi.fn()
  }
  return { ...actual, VoiceRecorder: FakeRecorder }
})

function audio(): TavernAudio {
  return {
    flush: vi.fn(),
    releaseAll: vi.fn(),
    queueChunk: vi.fn(),
    replay: vi.fn(),
    stop: vi.fn(),
    highlight: ref(null),
    playingIndex: ref(null),
  } as unknown as TavernAudio
}

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
  return { id: factId++, kind: 'npc', status: 'active', pending: false, portrait: null, ...partial }
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

describe('useTavernSession · HP 归属与确定性结算（docs/57 §3.2）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.fetchCampaigns.mockResolvedValue([{ id: 1, name: '迷雾酒馆' }])
  })

  it('玩家 HP 只取 pc.*.hp：敌人 npc.*.hp 不冒充玩家 HP；有 PC 实体时同名键优先', async () => {
    const session = useTavernSession(audio())

    mocks.fetchCampaignState.mockResolvedValue(
      makeState([fact('npc.蚀影.hp', '12'), fact('pc.主角.hp', '7/12')]),
    )
    await session.selectCampaign(1)
    expect(session.hp.value).toBe('7/12')

    // 只有敌人 HP → 顶栏不显示玩家 HP（不再取首个 .hp 事实）
    mocks.fetchCampaignState.mockResolvedValue(makeState([fact('npc.蚀影.hp', '12')]))
    await session.selectCampaign(1)
    expect(session.hp.value).toBeNull()

    // 多 PC 时优先自己实体同名的键
    mocks.fetchCampaignState.mockResolvedValue(
      makeState([fact('pc.旁白.hp', '3'), fact('pc.主角.hp', '9')], [entity({ kind: 'pc', name: '主角' })]),
    )
    await session.selectCampaign(1)
    expect(session.hp.value).toBe('9')
  })

  it('settleQuest 成功：调接口 + 结局行落地 + finished；幂等重复调用不阻断', async () => {
    const session = useTavernSession(audio())
    mocks.fetchCampaignState.mockResolvedValue(makeState([fact('quest.寻找戒指.progress', '6/6')]))
    await session.selectCampaign(1)
    expect(session.finished.value).toBe(false)

    mocks.settleQuest.mockResolvedValue({
      quest: '寻找戒指',
      outcome: 'strong',
      title: '圆满结局 · 寻找戒指',
      text: '你做到了。',
      epilogue: '多年以后。',
      finished: true,
    })
    const ok = await session.settleQuest('寻找戒指')
    expect(ok).toBe(true)
    expect(mocks.settleQuest).toHaveBeenCalledWith(1, '寻找戒指', undefined)
    expect(session.finished.value).toBe(true)
    const endingRows = session.rows.value.filter((r) => r.payload?.trpg_sys === 'ending')
    expect(endingRows).toHaveLength(1)
    expect(endingRows[0]!.payload?.quest).toBe('寻找戒指')
    expect(session.quest.ending.value?.title).toContain('圆满结局')
  })

  it('settleQuest 失败：回退文本行动（发「我想结算任务：X」）并返回 false', async () => {
    const session = useTavernSession(audio())
    mocks.fetchCampaignState.mockResolvedValue(makeState([]))
    await session.selectCampaign(1)

    mocks.settleQuest.mockRejectedValueOnce(new Error('接口不可用'))
    const ok = await session.settleQuest('寻找戒指')
    expect(ok).toBe(false)
    expect(session.inputError.value).toContain('接口不可用')
    expect(mocks.streamTrpgTurn).toHaveBeenCalled()
    const lastUser = [...session.rows.value].reverse().find((r) => r.role === 'user')
    expect(lastUser?.content).toBe('我想结算任务：寻找戒指')
  })
})
