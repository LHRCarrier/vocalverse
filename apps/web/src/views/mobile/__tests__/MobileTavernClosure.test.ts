import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { TrpgFactItem, TrpgState } from '@/api/trpg'
import type { TrpgSseEvent } from '@/audio/trpg-sse-types'
import MobileTavernView from '@/views/mobile/MobileTavernView.vue'

/**
 * 跑团闭环前端（docs/56 §6）：进度钟条 / 在场角色条 / character 事件 / 立绘事件开立绘展台 /
 * 尾声系统卡（刷新恢复路径）/ 遭遇事件驱动动作面板。
 * 与 MobileTavernView.test.ts 分开：原文件贴近 fe-08 行数上限。
 */
const mocks = vi.hoisted(() => ({
  onEvent: (() => undefined) as (e: TrpgSseEvent) => void,
  fetchCampaigns: {} as ReturnType<typeof vi.fn>,
  fetchCampaignState: {} as ReturnType<typeof vi.fn>,
  streamTrpgTurn: {} as ReturnType<typeof vi.fn>,
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
  mocks.fetchCards = vi.fn(async () => [])
  mocks.fetchPrefs = vi.fn(async () => ({ lang: 'zh', voice_enabled: true, voice_name: null }))
  return {
    fetchCampaigns: mocks.fetchCampaigns,
    fetchCampaignState: mocks.fetchCampaignState,
    streamTrpgTurn: mocks.streamTrpgTurn,
    fetchCards: mocks.fetchCards,
    fetchPrefs: mocks.fetchPrefs,
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
    facts: [fact('pc.主角.hp', '12/12')],
    tasks: [],
    clues: [],
    entities: [
      { id: 1, kind: 'pc', name: '主角', status: 'active', pending: false, portrait: null },
      { id: 2, kind: 'npc', name: '莉亚', status: 'active', pending: false, portrait: null },
    ],
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

async function sendTurn(wrapper: Awaited<ReturnType<typeof mountView>>) {
  await wrapper.find('input[aria-label="酒馆输入"]').setValue('我继续前进')
  await wrapper.find('button[aria-label="发送"]').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.clearAllMocks()
  mocks.fetchCampaignState.mockResolvedValue(baseState())
  mocks.fetchCards.mockResolvedValue([])
})

describe('酒馆闭环（docs/56/57）：进度钟 / 在场角色 / 立绘事件 / 尾声 / 遭遇', () => {
  it('quest 增量更新迷你条；展开出完整钟条；character「正在赶来」；portrait 开立绘展台', async () => {
    mocks.fetchCampaignState.mockResolvedValue(
      baseState({ facts: [fact('pc.主角.hp', '12/12'), fact('quest.寻找戒指.progress', '2/6')] }),
    )
    const wrapper = await mountView()
    expect(wrapper.find('.t-mini').text()).toContain('寻找戒指')
    expect(wrapper.find('.t-mini').text()).toContain('2/6')

    await sendTurn(wrapper)
    mocks.onEvent({
      type: 'quest',
      quest: '寻找戒指',
      progress: '5/6',
      segments: 6,
      kind: 'positive',
      full: false,
    })
    await flushPromises()
    expect(wrapper.find('.t-mini').text()).toContain('5/6')

    // 展开迷你条 → 完整钟条 + 在场条
    await wrapper.find('.t-mini__caret').trigger('click')
    expect(wrapper.find('.t-clock__num').text()).toBe('5/6')

    mocks.onEvent({ type: 'character', name: '老陈', kind: 'npc', status: 'arriving', note: '从后厨赶来' })
    await flushPromises()
    expect(wrapper.find('.t-cast__item.is-arriving').text()).toContain('正在赶来…')

    mocks.onEvent({
      type: 'portrait',
      entity: '老陈',
      kind: 'npc',
      mood: null,
      media_id: null,
      url: '/api/v1/media/m1',
    })
    await flushPromises()
    const sheet = wrapper.find('[role="dialog"][aria-label="角色立绘"]')
    expect(sheet.exists()).toBe(true)
    expect(sheet.text()).toContain('老陈')
    expect(sheet.find('.t-standee__img').attributes('src')).toBe('/api/v1/media/m1')

    await sheet.find('.t-sheet__close').trigger('click')
    expect(wrapper.find('[role="dialog"][aria-label="角色立绘"]').exists()).toBe(false)
  })

  it('ending 系统卡刷新渲染尾声卡；encounter start 驱动动作面板 + 战况卡', async () => {
    mocks.fetchCampaignState.mockResolvedValue(
      baseState({
        messages: [
          {
            id: 7,
            role: 'assistant',
            kind: 'system',
            content: '',
            payload: {
              trpg_sys: 'ending',
              quest: '寻找戒指',
              outcome: 'strong',
              title: '圆满结局 · 寻找戒指',
              text: '最好的收束。',
              epilogue: '多年以后。',
            },
            meta: null,
            audio_url: null,
            created_at: null,
          },
        ],
      }),
    )
    const wrapper = await mountView()
    expect(wrapper.find('.t-ending').text()).toContain('圆满结局')

    await sendTurn(wrapper)
    mocks.onEvent({
      type: 'encounter',
      kind: 'start',
      order: ['pc.主角', 'npc.莉亚'],
      turn: 0,
      round: 1,
    })
    await flushPromises()
    const panel = wrapper.find('.t-act-panel')
    expect(panel.exists()).toBe(true)
    expect(panel.find('.t-enc').text()).toContain('第 1 轮')
    expect(panel.find('.t-enc__pip.is-current').text()).toContain('主角')
    expect(panel.text()).toContain('攻击 莉亚')
  })

  it('ending 实时事件（系统卡未落/落晚）也渲染尾声卡；同任务系统卡到达不重复', async () => {
    const wrapper = await mountView()
    await sendTurn(wrapper)
    mocks.onEvent({
      type: 'ending',
      quest: '寻找戒指',
      outcome: 'strong',
      title: '圆满结局 · 寻找戒指',
      text: '最好的收束。',
      epilogue: '多年以后。',
    })
    await flushPromises()
    expect(wrapper.findAll('.t-ending')).toHaveLength(1)
    expect(wrapper.find('.t-ending').text()).toContain('圆满结局')

    // 系统卡随后到达：同任务 upsert → 仍只有一张
    mocks.onEvent({
      type: 'system',
      trpg_sys: 'ending',
      payload: {
        quest: '寻找戒指',
        outcome: 'strong',
        title: '圆满结局 · 寻找戒指',
        text: '最好的收束。',
        epilogue: '多年以后。',
      },
    })
    await flushPromises()
    expect(wrapper.findAll('.t-ending')).toHaveLength(1)
  })

  it('动态推荐行动：character 入场/quest 变化即刷新建议 chips', async () => {
    mocks.fetchCampaignState.mockResolvedValue(
      baseState({ facts: [fact('pc.主角.hp', '12/12'), fact('quest.寻找戒指.progress', '2/6')] }),
    )
    const wrapper = await mountView()
    const labels = () => wrapper.findAll('.t-act-chip--suggest').map((c) => c.text())
    expect(labels()).toEqual(['观察酒馆', '与莉亚交谈', '推进寻找戒指'])

    await sendTurn(wrapper)
    mocks.onEvent({ type: 'character', name: '老陈', kind: 'npc', status: 'active', note: null })
    await flushPromises()
    expect(labels()).toContain('与老陈交谈')

    mocks.onEvent({
      type: 'quest',
      quest: '寻找戒指',
      progress: '6/6',
      segments: 6,
      kind: 'positive',
      full: true,
    })
    await flushPromises()
    // 建议仍指向进行中任务；满格后出现「收尾本幕」
    expect(labels()).toContain('推进寻找戒指')
    expect(wrapper.find('.t-act-chip--settle').text()).toContain('收尾本幕')
  })

  it('流式节流跟随 + turn_end 兜底滚底（docs/57 §3.2）', async () => {
    const scrollSpy = vi.fn()
    vi.stubGlobal('scrollTo', scrollSpy)
    try {
      const wrapper = await mountView()
      await sendTurn(wrapper)
      scrollSpy.mockClear()

      mocks.onEvent({ type: 'text_delta', text: 'DM 开始叙述……' })
      await flushPromises()
      expect(scrollSpy).toHaveBeenCalledTimes(1) // 首个增量（节流窗口外）跟随

      scrollSpy.mockClear()
      mocks.onEvent({ type: 'turn_end', message_id: 3, usage: null })
      await flushPromises()
      expect(scrollSpy).toHaveBeenCalled() // turn_end 保证一次滚底
      const lastCall = scrollSpy.mock.calls[scrollSpy.mock.calls.length - 1]![0] as ScrollToOptions
      expect(lastCall.behavior).toBe('auto')
      wrapper.unmount()
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
