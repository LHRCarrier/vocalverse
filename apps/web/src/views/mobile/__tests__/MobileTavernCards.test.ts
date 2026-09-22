import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { TrpgState } from '@/api/trpg'
import MobileTavernView from '@/views/mobile/MobileTavernView.vue'

/** 酒馆设置 + 场景卡抽屉（docs/52 §12）：偏好写服务端、卡片列表/生成/开局/删除 */
const mocks = vi.hoisted(() => ({
  fetchCampaigns: {} as ReturnType<typeof vi.fn>,
  fetchCampaignState: {} as ReturnType<typeof vi.fn>,
  fetchCards: {} as ReturnType<typeof vi.fn>,
  createCard: {} as ReturnType<typeof vi.fn>,
  updateCard: {} as ReturnType<typeof vi.fn>,
  deleteCard: {} as ReturnType<typeof vi.fn>,
  generateCard: {} as ReturnType<typeof vi.fn>,
  startCard: {} as ReturnType<typeof vi.fn>,
  fetchPrefs: {} as ReturnType<typeof vi.fn>,
  updatePrefs: {} as ReturnType<typeof vi.fn>,
  recorders: [] as Array<{ onStop?: (blob: Blob, mime: string, ms: number) => void }>,
}))

vi.mock('@/api/trpg', () => {
  mocks.fetchCampaigns = vi.fn(async () => [{ id: 1, name: '迷雾酒馆' }])
  mocks.fetchCampaignState = vi.fn()
  mocks.fetchCards = vi.fn(async () => [])
  mocks.createCard = vi.fn()
  mocks.updateCard = vi.fn()
  mocks.deleteCard = vi.fn()
  mocks.generateCard = vi.fn()
  mocks.startCard = vi.fn()
  mocks.fetchPrefs = vi.fn(async () => ({
    lang: 'zh',
    voice_enabled: true,
    voice_name: null,
    persisted: true,
  }))
  mocks.updatePrefs = vi.fn(async (patch: Record<string, unknown>) => ({
    lang: 'zh',
    voice_enabled: true,
    voice_name: null,
    ...patch,
  }))
  return {
    fetchCampaigns: mocks.fetchCampaigns,
    fetchCampaignState: mocks.fetchCampaignState,
    fetchCards: mocks.fetchCards,
    createCard: mocks.createCard,
    updateCard: mocks.updateCard,
    deleteCard: mocks.deleteCard,
    generateCard: mocks.generateCard,
    startCard: mocks.startCard,
    fetchPrefs: mocks.fetchPrefs,
    updatePrefs: mocks.updatePrefs,
    streamTrpgTurn: vi.fn(),
    setScene: vi.fn(),
    editFact: vi.fn(),
    createTask: vi.fn(),
    createClue: vi.fn(),
    clearCampaignMessages: vi.fn(),
    rollDice: vi.fn(),
    refreshNarrative: vi.fn(),
    setTaskStatus: vi.fn(),
    setClueRecovered: vi.fn(),
  }
})

vi.mock('@/api/tts', () => ({ tts: vi.fn(async () => new Blob()) }))

vi.mock('@/audio/recorder', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/audio/recorder')>()
  class FakeRecorder {
    state = 'idle'
    onStateChange: ((s: string) => void) | null = null
    onStop: ((blob: Blob, mime: string, ms: number) => void) | null = null
    constructor() {
      mocks.recorders.push(this as unknown as (typeof mocks.recorders)[number])
    }
    start = vi.fn(async () => {
      this.state = 'recording'
    })
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
    facts: [],
    tasks: [],
    clues: [],
    entities: [],
    events: [],
    scene: '酒馆',
    snapshot: '',
    narrative_summary: '',
    verify: { dangling: [], gap: false, missing: [], patch_text: null, contradiction: false },
    ...overrides,
  }
}

function userCard(id: number, title: string) {
  return {
    id,
    owner_user_id: 1,
    source: 'user' as const,
    status: 'published' as const,
    title,
    language: 'zh' as const,
    tags: [],
    scene: '灯塔',
    opening_line: '风很大。',
    template: {},
    generated_by: 'llm',
  }
}

async function mountView() {
  await router.push('/m/tavern')
  await router.isReady()
  const wrapper = mount(MobileTavernView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

/** 游玩态打开场景卡抽屉：顶栏「切换剧本」→ 抽屉内「＋ 用场景卡开新局」 */
async function openCardsSheet(wrapper: Awaited<ReturnType<typeof mountView>>) {
  await wrapper.find('button[aria-label="切换剧本"]').trigger('click')
  await flushPromises()
  await wrapper.findAll('button').find((b) => b.text().includes('用场景卡开新局'))!.trigger('click')
  await flushPromises()
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.clearAllMocks()
  mocks.fetchCampaignState.mockResolvedValue(baseState())
  mocks.fetchCards.mockResolvedValue([])
  mocks.fetchPrefs.mockResolvedValue({
    lang: 'zh',
    voice_enabled: true,
    voice_name: null,
    persisted: true,
  })
})

describe('酒馆设置 + 场景卡（docs/52 §12）', () => {
  /**
   * 2026-09-21 组长反馈：标题居中 + 功能项可放左。
   * 2026-09-22 设计稿改版：新增「角色立绘」入口（游玩态左一）；游玩态去掉场景卡顶栏钮
   * （收敛进「切换剧本」抽屉的「＋ 用场景卡开新局」，docs/35 规则 5）→ 2:3 / 1:2 配平。
   * 结构断言 = 左右两组钮数配平；happy-dom 无布局，真实居中量由 Playwright 坐标实测。
   */
  it('顶栏配平：游玩态 立绘+设置 在左；无剧本态 设置 在左、场景卡在右', async () => {
    const wrapper = await mountView()
    expect(
      wrapper.findAll('.u-topbar__leftacts .u-topbar__act').map((b) => b.attributes('aria-label')),
    ).toEqual(['角色立绘', '酒馆设置'])
    expect(wrapper.findAll('.u-topbar__acts .u-topbar__act').map((b) => b.attributes('aria-label'))).toEqual([
      '切换剧本',
      '主持台',
      '离开',
    ])

    mocks.fetchCampaigns.mockResolvedValueOnce([])
    const onboarding = await mountView()
    expect(
      onboarding.findAll('.u-topbar__leftacts .u-topbar__act').map((b) => b.attributes('aria-label')),
    ).toEqual(['酒馆设置'])
    expect(onboarding.findAll('.u-topbar__acts .u-topbar__act').map((b) => b.attributes('aria-label'))).toEqual([
      '场景卡',
      '离开',
    ])
  })

  it('设置面板：语言切换与语音开关写服务端偏好；音色为预留禁用', async () => {
    const wrapper = await mountView()
    await wrapper.find('button[aria-label="酒馆设置"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"][aria-label="酒馆设置"]').exists()).toBe(true)

    await wrapper.findAll('button').find((b) => b.text() === 'English')!.trigger('click')
    await flushPromises()
    expect(mocks.updatePrefs).toHaveBeenCalledWith({ lang: 'en' })

    const voiceSwitch = wrapper.find('button[role="switch"]')
    expect(voiceSwitch.attributes('aria-checked')).toBe('true')
    await voiceSwitch.trigger('click')
    await flushPromises()
    expect(mocks.updatePrefs).toHaveBeenCalledWith({ voice_enabled: false })

    expect(
      wrapper.find('select[aria-label="音色（暂不可选）"]').attributes('disabled'),
    ).toBeDefined()
  })

  it('场景卡面板：我的卡/精选卡分组，点开局建新剧本', async () => {
    mocks.fetchCards.mockResolvedValue([
      userCard(11, '我的灯塔'),
      {
        ...userCard(12, '精选 · 雨夜驿站'),
        owner_user_id: null,
        source: 'admin',
        generated_by: 'manual',
      },
    ])
    mocks.startCard.mockResolvedValue(77)
    mocks.fetchCampaignState.mockResolvedValue(
      baseState({ campaign: { id: 77, name: '我的灯塔' } }),
    )

    const wrapper = await mountView()
    await openCardsSheet(wrapper)
    const text = wrapper.text()
    expect(text).toContain('我的场景卡')
    expect(text).toContain('精选场景卡')
    expect(text).toContain('雨夜驿站')

    await wrapper.findAll('button').find((b) => b.text() === '开局')!.trigger('click')
    await flushPromises()
    expect(mocks.startCard).toHaveBeenCalledWith(11)
    expect(mocks.fetchCampaignState).toHaveBeenCalledWith(77)
  })

  it('场景卡生成：关键词 → 草稿预览 → 保存并开局', async () => {
    mocks.generateCard.mockResolvedValue({
      title: '幽灵船',
      scene: '甲板',
      opening_line: '雾里传来铃声。',
      template: { tasks: ['查明铃声'] },
      language: 'zh',
    })
    mocks.createCard.mockResolvedValue(userCard(21, '幽灵船'))
    mocks.startCard.mockResolvedValue(88)

    const wrapper = await mountView()
    await openCardsSheet(wrapper)
    await wrapper.findAll('button').find((b) => b.text().includes('按关键词生成'))!.trigger('click')
    await flushPromises()
    await wrapper.find('input[aria-label="场景关键词"]').setValue('海盗 幽灵船')
    await wrapper.findAll('button').find((b) => b.text() === '生成卡片')!.trigger('click')
    await flushPromises()
    expect(mocks.generateCard).toHaveBeenCalledWith('海盗 幽灵船', 'zh')
    expect(wrapper.text()).toContain('幽灵船')

    await wrapper.findAll('button').find((b) => b.text() === '保存并开局')!.trigger('click')
    await flushPromises()
    expect(mocks.createCard).toHaveBeenCalled()
    expect(mocks.startCard).toHaveBeenCalledWith(21)
  })

  it('场景卡面板：删除我的卡走归档接口；编辑保存走更新接口', async () => {
    mocks.fetchCards.mockResolvedValue([userCard(31, '待改卡')])
    mocks.deleteCard.mockResolvedValue(undefined)
    mocks.updateCard.mockResolvedValue(userCard(31, '改过的卡'))

    const wrapper = await mountView()
    await openCardsSheet(wrapper)

    await wrapper.find('button[aria-label="编辑"]').trigger('click')
    await flushPromises()
    await wrapper.find('input[aria-label="编辑标题"]').setValue('改过的卡')
    await wrapper.findAll('button').find((b) => b.text() === '保存修改')!.trigger('click')
    await flushPromises()
    expect(mocks.updateCard).toHaveBeenCalledWith(
      31,
      expect.objectContaining({ title: '改过的卡' }),
    )

    await wrapper.find('button[aria-label="删除"]').trigger('click')
    await flushPromises()
    expect(mocks.deleteCard).toHaveBeenCalledWith(31)
  })
})
