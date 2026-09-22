import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { TrpgFactItem, TrpgState } from '@/api/trpg'
import type { TrpgSseEvent } from '@/audio/trpg-sse-types'
import MobileTavernView from '@/views/mobile/MobileTavernView.vue'

/**
 * 酒馆页内四视图导航（2026-09-22 实装）：
 * 大堂 / 酒馆跑团 / 角色卡 / 纪事 —— 同页切换内容区，底部导航常驻，游玩态不因切走而重载；
 * 已完结读 `campaign.finished`（P1-2），刷新后已完结条在、收尾钮不回潮。
 */
const mocks = vi.hoisted(() => ({
  onEvent: (() => undefined) as (e: TrpgSseEvent) => void,
  fetchCampaigns: {} as ReturnType<typeof vi.fn>,
  fetchCampaignState: {} as ReturnType<typeof vi.fn>,
  streamTrpgTurn: {} as ReturnType<typeof vi.fn>,
  clearCampaignMessages: {} as ReturnType<typeof vi.fn>,
  fetchCards: {} as ReturnType<typeof vi.fn>,
  fetchPrefs: {} as ReturnType<typeof vi.fn>,
}))

vi.mock('@/api/trpg', () => {
  mocks.fetchCampaigns = vi.fn(async () => [{ id: 1, name: '迷雾酒馆' }])
  mocks.fetchCampaignState = vi.fn()
  mocks.streamTrpgTurn = vi.fn(
    (_campaignId: number, _form: FormData, onEvent: (e: TrpgSseEvent) => void) => {
      mocks.onEvent = onEvent
    },
  )
  mocks.clearCampaignMessages = vi.fn(async () => 0)
  mocks.fetchCards = vi.fn(async () => [])
  mocks.fetchPrefs = vi.fn(async () => ({ lang: 'zh', voice_enabled: true, voice_name: null }))
  return {
    fetchCampaigns: mocks.fetchCampaigns,
    fetchCampaignState: mocks.fetchCampaignState,
    streamTrpgTurn: mocks.streamTrpgTurn,
    clearCampaignMessages: mocks.clearCampaignMessages,
    fetchCards: mocks.fetchCards,
    fetchPrefs: mocks.fetchPrefs,
    rollDice: vi.fn(),
    createCampaign: vi.fn(),
    setScene: vi.fn(),
    editFact: vi.fn(),
    createTask: vi.fn(),
    createClue: vi.fn(),
    deleteFact: vi.fn(),
    refreshNarrative: vi.fn(),
    setTaskStatus: vi.fn(),
    setClueRecovered: vi.fn(),
    createCard: vi.fn(),
    updateCard: vi.fn(),
    deleteCard: vi.fn(),
    generateCard: vi.fn(),
    startCard: vi.fn(),
    updatePrefs: vi.fn(),
    settleQuest: vi.fn(),
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
    messages: [
      {
        id: 9,
        role: 'assistant',
        kind: 'system',
        content: '',
        payload: {
          trpg_sys: 'ending',
          quest: '寻找戒指',
          outcome: 'strong',
          title: '圆满结局 · 寻找戒指',
          text: '你做到了。',
          epilogue: '多年以后。',
        },
        meta: null,
        audio_url: null,
        created_at: null,
      },
    ],
    facts: [fact('pc.主角.hp', '12/12'), fact('quest.寻找戒指.progress', '6/6')],
    tasks: [{ id: 1, title: '打听怪谈', status: 'active', scene: null, last_mentioned_at: null }],
    clues: [
      { id: 1, title: '暗门', content: '酒保提到过', scene: null, found: true, recovered: false, last_mentioned_at: null },
    ],
    entities: [
      { id: 1, kind: 'pc', name: '主角', status: 'active', pending: false, portrait: null },
      { id: 2, kind: 'npc', name: '莉亚', status: 'active', pending: false, portrait: null },
      { id: 3, kind: 'npc', name: '幽灵', status: 'cleared', pending: false, portrait: null },
    ],
    events: [{ id: 1, round: 2, summary: '抵达酒馆', created_at: null }],
    scene: '酒馆',
    snapshot: '',
    narrative_summary: '【摘要】钟声逼近。',
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
  mocks.fetchCards.mockResolvedValue([])
})

describe('酒馆页内导航（大堂 / 酒馆跑团 / 角色卡 / 纪事）', () => {
  it('切到大堂：真实视图 + 导航常驻、底部 dock 让位；回跑团保留正文不重载', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('input[aria-label="酒馆输入"]').exists()).toBe(true)
    const boots = mocks.fetchCampaignState.mock.calls.length

    await wrapper.find('button[aria-label="大堂"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.t-hall').exists()).toBe(true)
    expect(wrapper.find('.u-chat-dock').exists()).toBe(false)
    expect(wrapper.find('.t-nav').exists()).toBe(true)
    expect(wrapper.find('.t-nav__item--on').attributes('aria-label')).toBe('大堂')

    await wrapper.find('button[aria-label="酒馆跑团"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('input[aria-label="酒馆输入"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('迷雾酒馆')
    expect(mocks.fetchCampaignState.mock.calls.length).toBe(boots)
    expect(wrapper.find('.t-nav__item--on').attributes('aria-label')).toBe('酒馆跑团')
  })

  it('角色卡：PC 卡 + NPC 卡，点 NPC 开既有立绘展台（带在场状态）', async () => {
    const wrapper = await mountView()
    await wrapper.find('button[aria-label="角色卡"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.t-cards').exists()).toBe(true)
    expect(wrapper.find('.t-cards__pc').text()).toContain('主角')

    await wrapper.find('button[aria-label="查看 莉亚 的角色卡"]').trigger('click')
    await flushPromises()
    const sheet = wrapper.find('[role="dialog"][aria-label="角色立绘"]')
    expect(sheet.exists()).toBe(true)
    expect(sheet.text()).toContain('莉亚')
    expect(sheet.text()).toContain('在场')
  })

  it('纪事：摘要 / 编年史 / 任务线索 / 尾声渲染', async () => {
    const wrapper = await mountView()
    await wrapper.find('button[aria-label="纪事"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.t-chron').exists()).toBe(true)
    expect(wrapper.text()).toContain('钟声逼近')
    expect(wrapper.find('.t-chron__event').text()).toContain('抵达酒馆')
    expect(wrapper.text()).toContain('打听怪谈')
    expect(wrapper.find('.t-ending').text()).toContain('圆满结局')
  })

  it('大堂已完结（campaign.finished 刷新恢复）：已完结条在、收尾钮不回潮；切换/重开可用', async () => {
    mocks.fetchCampaigns.mockResolvedValue([
      { id: 1, name: '迷雾酒馆', finished: true, finished_at: '2026-09-22T10:00:00Z' },
      { id: 2, name: '雨夜驿站' },
    ])
    mocks.fetchCampaignState.mockResolvedValue(
      baseState({ campaign: { id: 1, name: '迷雾酒馆', narrative_summary: '', finished: true } }),
    )
    const wrapper = await mountView()

    // 刷新后的游玩态：已完结条在；满格任务也不出收尾钮
    expect(wrapper.find('.t-finished').exists()).toBe(true)
    expect(wrapper.find('.t-act-chip--settle').exists()).toBe(false)

    await wrapper.find('button[aria-label="大堂"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.t-hall__hero .t-hall__badge.is-done').text()).toBe('已完结')
    expect(wrapper.findAll('.t-hall__done')).toHaveLength(1)
    expect(wrapper.find('.t-hall__done').text()).toContain('迷雾酒馆')
    expect(wrapper.find('.t-hall__done-hint').text()).toContain('圆满结局 · 寻找戒指')

    await wrapper.find('button[aria-label="切换剧本 雨夜驿站"]').trigger('click')
    await flushPromises()
    expect(mocks.fetchCampaignState).toHaveBeenCalledWith(2)

    vi.stubGlobal('confirm', vi.fn(() => true))
    try {
      await wrapper.find('button[aria-label="重开本剧本"]').trigger('click')
      await flushPromises()
      expect(mocks.clearCampaignMessages).toHaveBeenCalledWith(2)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
