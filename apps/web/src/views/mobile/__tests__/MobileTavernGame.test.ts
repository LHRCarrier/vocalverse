import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { TrpgState } from '@/api/trpg'
import { useUiStore } from '@/stores/ui'
import MobileTavernView from '@/views/mobile/MobileTavernView.vue'

/**
 * 酒馆设计稿改版（2026-09-22）：
 * 页内底栏（大堂/酒馆跑团/角色卡/纪事，占位 toast）+ 角色立绘抽屉（占位立绘 + 真实 D20 检定）
 * + 输入 dock（推荐行动填入 / 骰钮）。
 */
const mocks = vi.hoisted(() => ({
  fetchCampaigns: {} as ReturnType<typeof vi.fn>,
  fetchCampaignState: {} as ReturnType<typeof vi.fn>,
  streamTrpgTurn: {} as ReturnType<typeof vi.fn>,
  rollDice: {} as ReturnType<typeof vi.fn>,
  fetchCards: {} as ReturnType<typeof vi.fn>,
  fetchPrefs: {} as ReturnType<typeof vi.fn>,
}))

vi.mock('@/api/trpg', () => {
  mocks.fetchCampaigns = vi.fn(async () => [{ id: 1, name: '迷雾酒馆' }])
  mocks.fetchCampaignState = vi.fn()
  mocks.streamTrpgTurn = vi.fn()
  mocks.rollDice = vi.fn()
  mocks.fetchCards = vi.fn(async () => [])
  mocks.fetchPrefs = vi.fn(async () => ({ lang: 'zh', voice_enabled: true, voice_name: null }))
  return {
    fetchCampaigns: mocks.fetchCampaigns,
    fetchCampaignState: mocks.fetchCampaignState,
    streamTrpgTurn: mocks.streamTrpgTurn,
    rollDice: mocks.rollDice,
    fetchCards: mocks.fetchCards,
    fetchPrefs: mocks.fetchPrefs,
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

function baseState(overrides: Partial<TrpgState> = {}): TrpgState {
  return {
    campaign: { id: 1, name: '迷雾酒馆', narrative_summary: '' },
    messages: [],
    facts: [
      {
        id: 1,
        key: 'pc.主角.hp',
        value: '12/12',
        kind: 'state',
        modality: 'fact',
        speaker: null,
        importance: 0.5,
        user_touched_at: null,
        user_deleted_at: null,
      },
      {
        id: 2,
        key: 'pc.主角.inventory',
        value: '短剑, 黄铜钥匙',
        kind: 'state',
        modality: 'fact',
        speaker: null,
        importance: 0.5,
        user_touched_at: null,
        user_deleted_at: null,
      },
    ],
    tasks: [{ id: 1, title: '打听怪谈', status: 'active', scene: '酒馆', last_mentioned_at: null }],
    clues: [],
    entities: [{ kind: 'npc', name: '莉亚', status: 'active', pending: false }],
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
  mocks.fetchCards.mockResolvedValue([])
  mocks.fetchPrefs.mockResolvedValue({ lang: 'zh', voice_enabled: true, voice_name: null })
  mocks.rollDice.mockResolvedValue({
    text: '掷出 15',
    summary: '第 1 回合：pc.主角.hp=7（-5）',
    state: baseState(),
  })
})

describe('酒馆设计稿改版（页内底栏 / 立绘抽屉 / dock）', () => {
  it('页内底栏：4 项导航渲染，占位项 toast 提示后续版本', async () => {
    const wrapper = await mountView()
    for (const label of ['大堂', '酒馆跑团', '角色卡', '纪事']) {
      expect(wrapper.find(`button[aria-label="${label}"]`).exists(), label).toBe(true)
    }

    const ui = useUiStore()
    await wrapper.find('button[aria-label="大堂"]').trigger('click')
    expect(ui.toastText).toContain('大堂')
    expect(ui.toastText).toContain('后续版本开放')

    await wrapper.find('button[aria-label="角色卡"]').trigger('click')
    expect(ui.toastText).toContain('角色卡')
    await wrapper.find('button[aria-label="纪事"]').trigger('click')
    expect(ui.toastText).toContain('纪事')
  })

  it('副本任务卡：目标取 active 首任务；行囊事实拆成标签；HP 分数画条', async () => {
    const wrapper = await mountView()
    const stage = wrapper.find('.t-stage')
    expect(stage.text()).toContain('目标：')
    expect(stage.text()).toContain('打听怪谈')
    expect(wrapper.findAll('.t-strip__inv-tag').map((n) => n.text())).toEqual(['短剑', '黄铜钥匙'])
    expect(wrapper.find('.t-strip__bar-fill').attributes('style')).toContain('width: 100%')
  })

  it('角色立绘抽屉：设计稿立绘 + DM/冒险者切换 + 属性检定走 D20 桌骰', async () => {
    const wrapper = await mountView()
    await wrapper.find('button[aria-label="角色立绘"]').trigger('click')
    await flushPromises()
    const sheet = wrapper.find('[role="dialog"][aria-label="角色立绘"]')
    expect(sheet.exists()).toBe(true)
    expect(sheet.text()).toContain('守密人 (DM)')
    expect(sheet.text()).toContain('立绘为设计稿占位图')
    expect(sheet.text()).toContain('属性系统后续开放')
    expect(sheet.find('.t-standee__img').attributes('src')).toContain('dm-standee.webp')

    await wrapper.findAll('[role="tab"]').find((b) => b.text().includes('冒险者'))!.trigger('click')
    expect(sheet.text()).toContain('跑团主角')
    expect(sheet.text()).toContain('🎒 短剑')
    expect(sheet.find('.t-standee__img').attributes('src')).toContain('pc-standee.webp')

    await wrapper.findAll('button').find((b) => b.text().includes('属性检定'))!.trigger('click')
    await flushPromises()
    expect(mocks.rollDice).toHaveBeenCalledWith(1, { dice: 'd20' })
    expect(useUiStore().toastText).toContain('检定已触发')
    // 检定后收起抽屉，让判定卡可见
    expect(wrapper.find('[role="dialog"][aria-label="角色立绘"]').exists()).toBe(false)

    await wrapper.find('button[aria-label="角色立绘"]').trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('返回冒险对话'))!.trigger('click')
    expect(wrapper.find('[role="dialog"][aria-label="角色立绘"]').exists()).toBe(false)
  })

  it('dock：推荐行动只填入不发送；骰钮触发 D20', async () => {
    const wrapper = await mountView()
    await wrapper.findAll('.t-quick__chip')[0]!.trigger('click')
    const input = wrapper.find('input[aria-label="酒馆输入"]')
    expect((input.element as HTMLInputElement).value).toBe('我仔细观察四周')
    expect(mocks.streamTrpgTurn).not.toHaveBeenCalled()

    await wrapper.find('button[aria-label="快速投骰 D20"]').trigger('click')
    await flushPromises()
    expect(mocks.rollDice).toHaveBeenCalledWith(1, { dice: 'd20' })
  })

  it('NPC 段渲染成插片卡（设计稿 npc-whisper-card）', async () => {
    mocks.fetchCampaignState.mockResolvedValue(
      baseState({
        messages: [
          {
            id: 1,
            role: 'assistant',
            kind: 'text',
            content: '你推开门。\n\n莉亚：这边坐。',
            payload: null,
            meta: null,
            audio_url: null,
            created_at: null,
          },
        ],
      }),
    )
    const wrapper = await mountView()
    const npc = wrapper.find('.t-npc-card')
    expect(npc.exists()).toBe(true)
    expect(npc.text()).toContain('莉亚')
    expect(npc.text()).toContain('这边坐')
  })
})
