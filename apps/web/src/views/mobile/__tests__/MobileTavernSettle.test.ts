import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { TrpgFactItem, TrpgState } from '@/api/trpg'
import type { TrpgSseEvent } from '@/audio/trpg-sse-types'
import MobileTavernView from '@/views/mobile/MobileTavernView.vue'

/**
 * 结算闭环（docs/57 §3.2/§4）：钟满「收尾本幕」→ 确定性 settle 接口 → 尾声卡 + 已完结条
 * + 开新篇章；失败回退文本行动；刷新后（state.finished）仍显示已完结。
 */
const mocks = vi.hoisted(() => ({
  onEvent: (() => undefined) as (e: TrpgSseEvent) => void,
  fetchCampaigns: {} as ReturnType<typeof vi.fn>,
  fetchCampaignState: {} as ReturnType<typeof vi.fn>,
  streamTrpgTurn: {} as ReturnType<typeof vi.fn>,
  settleQuest: {} as ReturnType<typeof vi.fn>,
}))

vi.mock('@/api/trpg', () => {
  mocks.fetchCampaigns = vi.fn(async () => [{ id: 1, name: '迷雾酒馆' }])
  mocks.fetchCampaignState = vi.fn()
  mocks.streamTrpgTurn = vi.fn(
    (_id: number, _form: FormData, onEvent: (e: TrpgSseEvent) => void) => {
      mocks.onEvent = onEvent
    },
  )
  mocks.settleQuest = vi.fn()
  return {
    fetchCampaigns: mocks.fetchCampaigns,
    fetchCampaignState: mocks.fetchCampaignState,
    streamTrpgTurn: mocks.streamTrpgTurn,
    settleQuest: mocks.settleQuest,
    fetchCards: vi.fn(async () => []),
    fetchPrefs: vi.fn(async () => ({ lang: 'zh', voice_enabled: true, voice_name: null })),
    rollDice: vi.fn(),
    createCampaign: vi.fn(),
    setScene: vi.fn(),
    editFact: vi.fn(),
    createTask: vi.fn(),
    createClue: vi.fn(),
    deleteFact: vi.fn(),
    clearCampaignMessages: vi.fn(),
    refreshNarrative: vi.fn(),
    setTaskStatus: vi.fn(),
    setClueRecovered: vi.fn(),
    createCard: vi.fn(),
    updateCard: vi.fn(),
    deleteCard: vi.fn(),
    generateCard: vi.fn(),
    startCard: vi.fn(),
    updatePrefs: vi.fn(),
  }
})

vi.mock('@/api/tts', () => ({ tts: vi.fn(async () => new Blob()) }))

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

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/tavern', component: MobileTavernView },
    { path: '/m/learn', component: { template: '<div/>' } },
    { path: '/m/home', component: { template: '<div/>' } },
  ],
})

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

function baseState(overrides: Partial<TrpgState> = {}): TrpgState {
  return {
    campaign: { id: 1, name: '迷雾酒馆', narrative_summary: '' },
    messages: [],
    facts: [
      fact('pc.主角.hp', '12/12'),
      fact('quest.寻找戒指.progress', '6/6'),
      fact('quest.寻找戒指.kind', 'positive'),
    ],
    tasks: [],
    clues: [],
    entities: [{ id: 1, kind: 'pc', name: '主角', status: 'active', pending: false, portrait: null }],
    events: [],
    scene: '酒馆',
    snapshot: '',
    narrative_summary: '',
    verify: { dangling: [], gap: false, missing: [], patch_text: null, contradiction: false },
    ...overrides,
  }
}

async function mountView() {
  await router.push('/m/tavern')
  await router.isReady()
  const wrapper = mount(MobileTavernView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.clearAllMocks()
  mocks.fetchCampaignState.mockResolvedValue(baseState())
  mocks.fetchCampaigns.mockResolvedValue([{ id: 1, name: '迷雾酒馆' }])
  mocks.settleQuest.mockResolvedValue({
    quest: '寻找戒指',
    outcome: 'strong',
    title: '圆满结局 · 寻找戒指',
    text: '你做到了。',
    epilogue: '多年以后。',
    finished: true,
  })
})

describe('酒馆结算闭环（docs/57 §3.2）', () => {
  it('钟满 → 收尾本幕 → 调 settle 接口 → 尾声卡 + 已完结条 + 开新篇章；结算后不再出收尾钮', async () => {
    const wrapper = await mountView()
    const settle = wrapper.find('.t-act-chip--settle')
    expect(settle.exists()).toBe(true)
    expect(settle.text()).toContain('收尾本幕 · 寻找戒指')

    const campaignsBefore = mocks.fetchCampaigns.mock.calls.length
    await settle.trigger('click')
    await flushPromises()
    expect(mocks.settleQuest).toHaveBeenCalledWith(1, '寻找戒指', undefined)
    // 结算后同时刷列表（大堂「已完结」分组靠列表 finished）
    expect(mocks.fetchCampaigns.mock.calls.length).toBeGreaterThan(campaignsBefore)

    // 实时返回的结局走同一渲染路径（不用等系统卡）
    expect(wrapper.find('.t-ending').text()).toContain('圆满结局')
    // 已完结条 + 开新篇章
    const finished = wrapper.find('.t-finished')
    expect(finished.exists()).toBe(true)
    expect(finished.text()).toContain('本局已完结')
    expect(finished.find('.t-finished__btn').text()).toBe('开新篇章')
    // 已结算：收尾钮消失
    expect(wrapper.find('.t-act-chip--settle').exists()).toBe(false)

    await finished.find('.t-finished__btn').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"][aria-label="选择剧本"]').exists()).toBe(true)
  })

  it('刷新恢复：state.campaign.finished=true（权威契约）→ 已完结条常驻、收尾钮不回潮', async () => {
    mocks.fetchCampaignState.mockResolvedValue(
      baseState({
        campaign: {
          id: 1,
          name: '迷雾酒馆',
          narrative_summary: '',
          finished: true,
          finished_at: '2026-09-22T12:00:00Z',
        },
      }),
    )
    const wrapper = await mountView()
    expect(wrapper.find('.t-finished').exists()).toBe(true)
    expect(wrapper.find('.t-act-chip--settle').exists()).toBe(false)
  })

  it('旧契约兼容：仅顶层 finished=true 也认已完结（不因后端灰度闪断）', async () => {
    mocks.fetchCampaignState.mockResolvedValue(
      baseState({ finished: true, finished_at: '2026-09-22T12:00:00Z' }),
    )
    const wrapper = await mountView()
    expect(wrapper.find('.t-finished').exists()).toBe(true)
    expect(wrapper.find('.t-act-chip--settle').exists()).toBe(false)
  })

  it('结算接口失败 → 回退文本行动（发「我想结算任务：X」）', async () => {
    mocks.settleQuest.mockRejectedValueOnce(new Error('网络中断'))
    const wrapper = await mountView()
    await wrapper.find('.t-act-chip--settle').trigger('click')
    await flushPromises()
    expect(mocks.streamTrpgTurn).toHaveBeenCalled()
    expect(wrapper.text()).toContain('我想结算任务：寻找戒指')
    expect(wrapper.text()).toContain('网络中断')
  })

  it('尾声实时事件先到、系统卡后到：同任务只渲染一张尾声卡', async () => {
    const wrapper = await mountView()
    await wrapper.find('input[aria-label="酒馆输入"]').setValue('我继续')
    await wrapper.find('button[aria-label="发送"]').trigger('click')
    mocks.onEvent({
      type: 'ending',
      quest: '寻找戒指',
      outcome: 'weak',
      title: '尘埃落定 · 寻找戒指',
      text: '代价与收获并存。',
      epilogue: '账留给下次相遇。',
    })
    await flushPromises()
    expect(wrapper.findAll('.t-ending')).toHaveLength(1)

    mocks.onEvent({
      type: 'system',
      trpg_sys: 'ending',
      payload: {
        quest: '寻找戒指',
        outcome: 'weak',
        title: '尘埃落定 · 寻找戒指',
        text: '代价与收获并存。',
        epilogue: '账留给下次相遇。',
      },
    })
    await flushPromises()
    expect(wrapper.findAll('.t-ending')).toHaveLength(1)
  })
})
