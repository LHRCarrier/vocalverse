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
    entities: [{ id: 1, kind: 'npc', name: '莉亚', status: 'active', pending: false, portrait: null }],
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
  it('页内底栏：4 项导航渲染，当前项标记 aria-current（不再是占位 toast）', async () => {
    const wrapper = await mountView()
    for (const label of ['大堂', '酒馆跑团', '角色卡', '纪事']) {
      expect(wrapper.find(`button[aria-label="${label}"]`).exists(), label).toBe(true)
    }

    const current = wrapper.find('button[aria-label="酒馆跑团"]')
    expect(current.attributes('aria-current')).toBe('page')
    expect(current.classes()).toContain('t-nav__item--on')
    expect(wrapper.find('button[aria-label="大堂"]').attributes('aria-current')).toBeUndefined()

    const ui = useUiStore()
    await wrapper.find('button[aria-label="大堂"]').trigger('click')
    expect(ui.toastText).not.toContain('后续版本开放')
    expect(wrapper.find('.t-hall').exists()).toBe(true)
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

  it('动作面板建议 chips：点击只填入输入框不发流；骰钮触发 D20', async () => {
    const wrapper = await mountView()
    const chips = wrapper.findAll('.t-act-chip--suggest')
    expect(chips.map((c) => c.text())).toEqual(['观察酒馆', '与莉亚交谈', '推进打听怪谈'])
    await chips[0]!.trigger('click')
    const input = wrapper.find('input[aria-label="酒馆输入"]')
    expect((input.element as HTMLInputElement).value).toBe('我仔细观察酒馆')
    expect(mocks.streamTrpgTurn).not.toHaveBeenCalled()

    await wrapper.find('button[aria-label="快速投骰 D20"]').trigger('click')
    await flushPromises()
    expect(mocks.rollDice).toHaveBeenCalledWith(1, { dice: 'd20' })
  })

  it('dock 不再有第二排推荐行动（单排建议在动作面板内）', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('.t-quick__row').exists()).toBe(false)
    expect(wrapper.findAll('.t-act-panel__row')).toHaveLength(1)
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

  it('迷你状态条：任务/在场常驻；展开出完整钟条与在场条；动作面板常驻单行（无遭遇无攻击）', async () => {
    const facts = baseState().facts
    mocks.fetchCampaignState.mockResolvedValue(
      baseState({
        facts: [
          ...facts,
          {
            id: 10,
            key: 'quest.寻找戒指.progress',
            value: '3/6',
            kind: 'state',
            modality: 'fact',
            speaker: null,
            importance: 0.5,
            user_touched_at: null,
            user_deleted_at: null,
          },
          {
            id: 11,
            key: 'item.治疗药水.qty',
            value: '2',
            kind: 'state',
            modality: 'fact',
            speaker: null,
            importance: 0.5,
            user_touched_at: null,
            user_deleted_at: null,
          },
          {
            id: 12,
            key: 'item.治疗药水.owner',
            value: 'pc.主角',
            kind: 'state',
            modality: 'fact',
            speaker: null,
            importance: 0.5,
            user_touched_at: null,
            user_deleted_at: null,
          },
        ],
      }),
    )
    const wrapper = await mountView()

    // 折叠态：正文里不再常驻大钟条/在场条，迷你条一行可见
    const mini = wrapper.find('.t-mini')
    expect(mini.exists()).toBe(true)
    expect(mini.text()).toContain('寻找戒指')
    expect(mini.text()).toContain('3/6')
    expect(mini.text()).toContain('在场 1')
    expect(wrapper.find('.t-clock').exists()).toBe(false)
    expect(wrapper.find('.t-cast__item').exists()).toBe(false)

    // 展开：完整钟条 + 在场条
    await wrapper.find('.t-mini__caret').trigger('click')
    expect(wrapper.find('.t-clock').text()).toContain('寻找戒指')
    expect(wrapper.find('.t-clock__num').text()).toBe('3/6')
    expect(wrapper.find('.t-cast__item').text()).toContain('莉亚')

    // 动作面板常驻单行：道具可点、无遭遇不出攻击
    const panel = wrapper.find('.t-act-panel')
    expect(panel.exists()).toBe(true)
    expect(panel.findAll('.t-act-panel__row')).toHaveLength(1)
    expect(panel.find('.t-act-chip--attack').exists()).toBe(false)
    expect(panel.text()).toContain('治疗药水')
    expect(panel.findAll('.t-act-chip--suggest')).toHaveLength(3)

    await panel.find('.t-act-chip--item').trigger('click')
    await flushPromises()
    expect(mocks.streamTrpgTurn).toHaveBeenCalled()
  })

  it('展开迷你条：停靠区变高时做滚动补偿（N8，不盖住正文）', async () => {
    const scrollBySpy = vi.fn()
    vi.stubGlobal('scrollBy', scrollBySpy)
    const rect = (height: number) =>
      ({ x: 0, y: 0, top: 0, left: 0, right: 390, bottom: height, width: 390, height, toJSON: () => ({}) }) as DOMRect
    const rectSpy = vi
      .spyOn(Element.prototype, 'getBoundingClientRect')
      .mockImplementation(function (this: Element) {
        // 停靠区展开后（迷你条 is-open）高度 240 → 420，差值 180 应被滚动补偿
        const expanded = !!this.classList?.contains('u-chat-dock') && !!this.querySelector('.t-mini.is-open')
        return rect(expanded ? 420 : 240)
      })
    try {
      const wrapper = await mountView()
      await wrapper.find('.t-mini__caret').trigger('click')
      await flushPromises()
      expect(wrapper.classes()).toContain('t-page--bars')
      expect(scrollBySpy).toHaveBeenCalledWith({ top: 180, behavior: 'auto' })
      wrapper.unmount()
    } finally {
      rectSpy.mockRestore()
      vi.unstubAllGlobals()
    }
  })

  it('迷你状态条线索入口：直达主持台「任务线索」页', async () => {
    mocks.fetchCampaignState.mockResolvedValue(
      baseState({
        clues: [
          {
            id: 1,
            title: '地下室里的暗门',
            content: '酒保提到过',
            scene: '酒馆',
            found: true,
            recovered: false,
            last_mentioned_at: null,
          },
        ],
      }),
    )
    const wrapper = await mountView()
    expect(wrapper.find('.t-mini__clue').text()).toContain('1')
    await wrapper.find('.t-mini__clue').trigger('click')
    await flushPromises()
    expect(wrapper.find('.t-sheet__panel').exists()).toBe(true)
    const activeTab = wrapper
      .findAll('.t-sheet__tabs button')
      .find((b) => b.classes().includes('is-on'))
    expect(activeTab?.text()).toBe('任务线索')
  })
})
