import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { TrpgState } from '@/api/trpg'
import type { TrpgSseEvent } from '@/audio/trpg-sse-types'
import MobileTavernView from '@/views/mobile/MobileTavernView.vue'

/** vi.mock 工厂外可写状态：捕获 streamTrpgTurn 的 onEvent（驱动 SSE 流） */
const mocks = vi.hoisted(() => ({
  events: [] as TrpgSseEvent[],
  closeHandler: (() => undefined) as () => void,
  errorHandler: (() => undefined) as (e: unknown) => void,
  recorders: [] as Array<{
    state: string
    start: (max?: number) => Promise<void>
    stop: () => void
    cancel: () => void
    onStop?: (blob: Blob, mime: string, durationMs: number) => void
    onStateChange?: (s: string) => void
  }>,
  streamTrpgTurn: {} as ReturnType<typeof vi.fn>,
  fetchCampaigns: {} as ReturnType<typeof vi.fn>,
  createCampaign: {} as ReturnType<typeof vi.fn>,
  fetchCampaignState: {} as ReturnType<typeof vi.fn>,
  setScene: {} as ReturnType<typeof vi.fn>,
  editFact: {} as ReturnType<typeof vi.fn>,
  createTask: {} as ReturnType<typeof vi.fn>,
  createClue: {} as ReturnType<typeof vi.fn>,
  deleteFact: {} as ReturnType<typeof vi.fn>,
  clearCampaignMessages: {} as ReturnType<typeof vi.fn>,
  rollDice: {} as ReturnType<typeof vi.fn>,
  refreshNarrative: {} as ReturnType<typeof vi.fn>,
  setTaskStatus: {} as ReturnType<typeof vi.fn>,
  setClueRecovered: {} as ReturnType<typeof vi.fn>,
  tts: {} as ReturnType<typeof vi.fn>,
  fetchCards: {} as ReturnType<typeof vi.fn>,
  fetchPrefs: {} as ReturnType<typeof vi.fn>,
}))

vi.mock('@/api/trpg', () => {
  mocks.fetchCampaigns = vi.fn()
  mocks.createCampaign = vi.fn()
  mocks.fetchCampaignState = vi.fn()
  mocks.streamTrpgTurn = vi.fn(
    (
      _campaignId: number,
      _form: FormData,
      onEvent: (e: TrpgSseEvent) => void,
      onError: (e: unknown) => void,
      onClose: () => void,
    ) => {
      mocks.events = []
      mocks.closeHandler = onClose
      mocks.errorHandler = onError
      // 由测试逐条 push 事件后调用 mocks.closeHandler()
      ;(globalThis as Record<string, unknown>).__trpgOnEvent = onEvent
    },
  )
  mocks.setScene = vi.fn()
  mocks.editFact = vi.fn()
  mocks.createTask = vi.fn()
  mocks.createClue = vi.fn()
  mocks.deleteFact = vi.fn()
  mocks.clearCampaignMessages = vi.fn()
  mocks.rollDice = vi.fn()
  mocks.refreshNarrative = vi.fn()
  mocks.setTaskStatus = vi.fn()
  mocks.setClueRecovered = vi.fn()
  mocks.fetchCards = vi.fn(async () => [])
  mocks.fetchPrefs = vi.fn(async () => ({ lang: 'zh', voice_enabled: true, voice_name: null }))
  return {
    fetchCampaigns: mocks.fetchCampaigns,
    createCampaign: mocks.createCampaign,
    fetchCampaignState: mocks.fetchCampaignState,
    streamTrpgTurn: mocks.streamTrpgTurn,
    setScene: mocks.setScene,
    editFact: mocks.editFact,
    createTask: mocks.createTask,
    createClue: mocks.createClue,
    deleteFact: mocks.deleteFact,
    clearCampaignMessages: mocks.clearCampaignMessages,
    rollDice: mocks.rollDice,
    refreshNarrative: mocks.refreshNarrative,
    setTaskStatus: mocks.setTaskStatus,
    setClueRecovered: mocks.setClueRecovered,
    fetchCards: mocks.fetchCards,
    fetchPrefs: mocks.fetchPrefs,
    createCard: vi.fn(),
    updateCard: vi.fn(),
    deleteCard: vi.fn(),
    generateCard: vi.fn(),
    startCard: vi.fn(),
    updatePrefs: vi.fn(),
  }
})

vi.mock('@/api/tts', () => {
  mocks.tts = vi.fn(async () => new Blob())
  return { tts: mocks.tts }
})

vi.mock('@/audio/recorder', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/audio/recorder')>()
  class FakeRecorder {
    state = 'idle'
    onStateChange: ((s: string) => void) | null = null
    onStop: ((blob: Blob, mime: string, durationMs: number) => void) | null = null
    constructor() {
      mocks.recorders.push(this as unknown as (typeof mocks.recorders)[number])
    }
    start = vi.fn(async () => {
      this.state = 'recording'
      this.onStateChange?.('recording')
    })
    stop = vi.fn()
    cancel = vi.fn()
  }
  return { ...actual, VoiceRecorder: FakeRecorder, MIN_RECORD_MS: actual.MIN_RECORD_MS }
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/tavern', component: MobileTavernView },
    { path: '/m/learn', component: { template: '<div/>' } },
    { path: '/m/home', component: { template: '<div/>' } },
  ],
})

function baseState(overrides: Partial<TrpgState> = {}): TrpgState {
  return {
    campaign: { id: 1, name: '迷雾酒馆', narrative_summary: '【当前状态】\nPC：HP 12' },
    messages: [],
    facts: [
      {
        id: 1,
        key: 'pc.主角.hp',
        value: '12',
        kind: 'state',
        modality: 'fact',
        speaker: null,
        importance: 0.5,
        user_touched_at: null,
        user_deleted_at: null,
      },
      {
        id: 2,
        key: 'pc.主角.location',
        value: '吧台',
        kind: 'state',
        modality: 'fact',
        speaker: null,
        importance: 0.5,
        user_touched_at: null,
        user_deleted_at: null,
      },
      {
        id: 3,
        key: 'rel.莉亚.attitude',
        value: '敌对',
        kind: 'fact',
        modality: 'claim',
        speaker: '莉亚',
        importance: 0.9,
        user_touched_at: null,
        user_deleted_at: null,
      },
    ],
    tasks: [{ id: 1, title: '打听怪谈', status: 'active', scene: '酒馆', last_mentioned_at: null }],
    clues: [],
    entities: [{ id: 1, kind: 'npc', name: '莉亚', status: 'active', pending: false, portrait: null }],
    events: [],
    scene: '酒馆',
    snapshot: '【当前状态】\nPC：HP 12',
    narrative_summary: '【当前状态】\nPC：HP 12',
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

function emit(event: TrpgSseEvent) {
  const fn = (globalThis as Record<string, unknown>).__trpgOnEvent as (e: TrpgSseEvent) => void
  fn(event)
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.clearAllMocks()
  mocks.recorders.length = 0
  mocks.fetchCampaignState.mockResolvedValue(baseState())
  mocks.fetchCampaigns.mockResolvedValue([{ id: 1, name: '迷雾酒馆' }])
})

describe('MobileTavernView（酒馆 · 剧本/回合/系统卡）', () => {
  it('有剧本 → 进游玩态：副本任务卡/HP/场景渲染', async () => {
    const wrapper = await mountView()
    const text = wrapper.text()
    expect(text).toContain('迷雾酒馆')
    expect(text).toContain('HP 12')
    expect(text).toContain('吧台')
    expect(text).toContain('待办 1')
    expect(text).toContain('目标：')
  })

  it('无剧本 → 开局引导；示例剧本一键开局（场景/HP/任务/线索）', async () => {
    mocks.fetchCampaigns.mockResolvedValueOnce([])
    mocks.createCampaign.mockResolvedValue({ id: 9, name: '迷雾酒馆' })
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('开一局跑团')
    expect(wrapper.text()).toContain('示例剧本')

    await wrapper.findAll('button').find((b) => b.text().includes('迷雾酒馆'))!.trigger('click')
    await flushPromises()
    expect(mocks.createCampaign).toHaveBeenCalledWith('迷雾酒馆')
    expect(mocks.setScene).toHaveBeenCalledWith(9, '酒馆')
    expect(mocks.editFact).toHaveBeenCalledWith(9, 'pc.主角.hp', '12')
    expect(mocks.createTask).toHaveBeenCalled()
    expect(mocks.createClue).toHaveBeenCalled()
    expect(mocks.fetchCampaignState).toHaveBeenCalledWith(9)
  })

  it('文本回合：用户气泡 + DM 流式正文 + NPC 分段 + 系统卡 + 判定卡', async () => {
    const wrapper = await mountView()
    const input = wrapper.find('input[aria-label="酒馆输入"]')
    await input.setValue('我走向吧台')
    await wrapper.find('button[aria-label="发送"]').trigger('click')

    // 动作已发流
    expect(mocks.streamTrpgTurn).toHaveBeenCalled()
    expect(wrapper.text()).toContain('我走向吧台')

    emit({ type: 'text_delta', text: 'DM：' })
    emit({ type: 'text_delta', text: '欢迎来到迷雾酒馆。' })
    emit({
      type: 'system',
      trpg_sys: 'dice',
      payload: { text: '第 1 回合：pc.主角.hp=7（-5）（骰 15 对抗 12 成功）' },
    })
    emit({ type: 'turn_end', message_id: 2, usage: null })
    mocks.closeHandler()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('欢迎来到迷雾酒馆')
    expect(text).toContain('判定')
    expect(text).toContain('主角 HP 7') // 内部键名 pc.主角.hp=7 已玩家化
    expect(text).not.toContain('pc.主角.hp=')
    // 回合结束（流关闭）→ 状态刷新（事实/任务对齐）
    expect(mocks.fetchCampaignState.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('NPC 台词渲染成人名标签段（实体表 kind=npc 驱动）', async () => {
    mocks.fetchCampaignState.mockResolvedValue(
      baseState({
        messages: [
          {
            id: 1,
            role: 'assistant',
            kind: 'text',
            content: '你推开木门。\n\n莉亚：这边坐。',
            payload: null,
            meta: null,
            audio_url: null,
            created_at: null,
          },
        ],
      }),
    )
    const wrapper = await mountView()
    const segs = wrapper.findAll('.t-npc-card')
    expect(segs).toHaveLength(1)
    expect(segs[0]!.text()).toContain('莉亚')
    expect(segs[0]!.text()).toContain('这边坐')
  })

  it('开场系统卡（open）：剧本名 + 场景 + 任务', async () => {
    mocks.fetchCampaignState.mockResolvedValue(
      baseState({
        messages: [
          {
            id: 1,
            role: 'assistant',
            kind: 'system',
            content: '',
            payload: { trpg_sys: 'open', campaign_name: '迷雾酒馆', scene: '酒馆', tasks: ['打听怪谈'] },
            meta: null,
            audio_url: null,
            created_at: null,
          },
        ],
      }),
    )
    const wrapper = await mountView()
    expect(wrapper.find('.t-card--open').text()).toContain('迷雾酒馆')
    expect(wrapper.find('.t-card--open').text()).toContain('打听怪谈')
  })

  it('语音回合：音频表单 + ASR 转写回填用户气泡', async () => {
    const wrapper = await mountView()
    await wrapper.find('button[aria-label="语音行动"]').trigger('click')
    await flushPromises()
    const recorder = mocks.recorders[mocks.recorders.length - 1]!
    recorder.onStop?.(new Blob(['x']), 'audio/webm', 2500)
    await flushPromises()
    expect(mocks.streamTrpgTurn).toHaveBeenCalled()
    emit({ type: 'user_transcript', text: '我去问问酒保', audio_url: '/api/v1/audio/a.mp3', words: null })
    await flushPromises()
    expect(wrapper.text()).toContain('我去问问酒保')
  })

  it('主持台：事实表可编辑/删除、任务状态、桌骰结果落卡', async () => {
    mocks.rollDice.mockResolvedValue({
      text: '掷出 15，对抗 12，成功',
      summary: '第 1 回合：pc.主角.hp=7（-5）',
      state: baseState(),
    })
    const wrapper = await mountView()
    await wrapper.find('button[aria-label="主持台"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.t-sheet__panel').text()).toContain('主持台')

    // 事实表 tab
    const factsTab = wrapper.findAll('.t-sheet__tabs button').find((b) => b.text() === '事实表')!
    await factsTab.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('pc.主角.hp')

    const editBtn = wrapper.findAll('.t-fact__ops button[title="编辑"]')[0]!
    await editBtn.trigger('click')
    await wrapper.find('input[aria-label="修改事实值"]').setValue('7')
    await wrapper.findAll('button').find((b) => b.text() === '保存')!.trigger('click')
    await flushPromises()
    expect(mocks.editFact).toHaveBeenCalledWith(1, 'pc.主角.hp', '7')

    const delBtn = wrapper.findAll('.t-fact__ops button[title="删除（墓碑，AI 不再复活）"]')[0]!
    await delBtn.trigger('click')
    await flushPromises()
    expect(mocks.deleteFact).toHaveBeenCalledWith(1, 'pc.主角.hp')

    // 任务线索 tab
    await wrapper.findAll('.t-sheet__tabs button').find((b) => b.text() === '任务线索')!.trigger('click')
    await flushPromises()
    await wrapper.find('input[aria-label="新任务标题"]').setValue('找戒指')
    await wrapper.findAll('button').find((b) => b.text() === '添加')!.trigger('click')
    await flushPromises()
    expect(mocks.createTask).toHaveBeenCalled()

    // 桌骰 tab
    await wrapper.findAll('.t-sheet__tabs button').find((b) => b.text() === '桌骰')!.trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '掷骰')!.trigger('click')
    await flushPromises()
    expect(mocks.rollDice).toHaveBeenCalledWith(1, expect.objectContaining({ dice: 'd20' }))
    expect(wrapper.text()).toContain('主角 HP 7')
  })

  it('流内错误提示（error 事件 + onError）', async () => {
    const wrapper = await mountView()
    await wrapper.find('input[aria-label="酒馆输入"]').setValue('我试一下')
    await wrapper.find('button[aria-label="发送"]').trigger('click')
    await flushPromises()
    emit({ type: 'error', code: 'llm_failed', recoverable: true })
    await flushPromises()
    expect(wrapper.text()).toContain('llm_failed')

    mocks.errorHandler(new Error('网络中断'))
    await flushPromises()
    expect(wrapper.text()).toContain('网络中断')
  })
})
