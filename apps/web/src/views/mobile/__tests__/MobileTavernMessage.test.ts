import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { TrpgState } from '@/api/trpg'
import type { TrpgSseEvent } from '@/audio/trpg-sse-types'
import MobileTavernView from '@/views/mobile/MobileTavernView.vue'

/** 消息流交互（2026-09-21 改造）：audio_chunk 逐词高亮 + 长按操作菜单（听/标注/复制） */
const mocks = vi.hoisted(() => ({
  onEvent: (() => undefined) as (e: TrpgSseEvent) => void,
  closeHandler: () => undefined as void,
  tts: {} as ReturnType<typeof vi.fn>,
  streamTrpgTurn: {} as ReturnType<typeof vi.fn>,
  fetchCampaignState: {} as ReturnType<typeof vi.fn>,
  fetchCampaigns: {} as ReturnType<typeof vi.fn>,
}))

vi.mock('@/api/trpg', () => {
  mocks.fetchCampaigns = vi.fn(async () => [{ id: 1, name: '迷雾酒馆' }])
  mocks.fetchCampaignState = vi.fn()
  mocks.streamTrpgTurn = vi.fn(
    (
      _id: number,
      _form: FormData,
      onEvent: (e: TrpgSseEvent) => void,
      _onError: (e: unknown) => void,
      onClose: () => void,
    ) => {
      mocks.onEvent = onEvent
      mocks.closeHandler = onClose
    },
  )
  return {
    fetchCampaigns: mocks.fetchCampaigns,
    fetchCampaignState: mocks.fetchCampaignState,
    streamTrpgTurn: mocks.streamTrpgTurn,
    fetchCards: vi.fn(async () => []),
    fetchPrefs: vi.fn(async () => ({ lang: 'zh', voice_enabled: true, voice_name: null })),
    createCard: vi.fn(),
    updateCard: vi.fn(),
    deleteCard: vi.fn(),
    generateCard: vi.fn(),
    startCard: vi.fn(),
    updatePrefs: vi.fn(),
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

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    // 音频块播放：happy-dom 无真实音频，桩掉 blob 拉取（避免 ECONNREFUSED 噪声）
    loadAudioBlob: vi.fn(async () => new Blob(['audio'], { type: 'audio/mpeg' })),
  }
})

vi.mock('@/api/tts', () => {
  mocks.tts = vi.fn(async () => new Blob(['audio'], { type: 'audio/mpeg' }))
  return { tts: mocks.tts }
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
    messages: [
      {
        id: 12,
        role: 'assistant',
        kind: 'text',
        content: '你推开酒馆的门。莉亚在角落里朝你举杯。',
        payload: null,
        meta: null,
        audio_url: null,
        created_at: null,
      },
    ],
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

async function mountView() {
  await router.push('/m/tavern')
  await router.isReady()
  const wrapper = mount(MobileTavernView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

function emit(event: TrpgSseEvent) {
  mocks.onEvent(event)
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.clearAllMocks()
  mocks.fetchCampaignState.mockResolvedValue(baseState())
})

describe('酒馆消息交互（逐词高亮 + 长按菜单）', () => {
  it('audio_chunk 带句子文本/偏移 → 该句 token 点亮（卡拉OK）', async () => {
    const wrapper = await mountView()
    await wrapper.find('input[aria-label="酒馆输入"]').setValue('我走向吧台')
    await wrapper.find('button[aria-label="发送"]').trigger('click')

    emit({ type: 'text_delta', text: '你走近吧台。' })
    emit({ type: 'turn_end', message_id: 9, usage: null })
    emit({
      type: 'audio_chunk',
      url: '/api/v1/audio/tts/x.mp3',
      duration: 2,
      text: '你走近吧台。',
      offset: 0,
    })
    await flushPromises()
    // 入队即按 offset 定位并点亮当前句首 token（播放进度随后推进）
    const lit = wrapper.findAll('.t-tok.is-lit').map((n) => n.text()).join('')
    expect(lit).toContain('你')
    expect(lit).not.toContain('吧台')
    expect(wrapper.find('.u-replay').exists()).toBe(false)
  })

  it('长按 DM 消息 → 操作菜单；标注/取消标注 + 复制', async () => {
    const writeText = vi.fn(async () => undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    vi.useFakeTimers()
    try {
      const wrapper = await mountView()
      const dm = wrapper.findAll('.t-msg')[0]!
      await dm.trigger('touchstart')
      vi.advanceTimersByTime(500)
      await flushPromises()
      expect(wrapper.find('[role="dialog"][aria-label="消息操作"]').exists()).toBe(true)

      await wrapper.findAll('button').find((b) => b.text().includes('标注这条'))!.trigger('click')
      await flushPromises()
      expect(wrapper.text()).toContain('已标注')

      // 再长按 → 取消标注
      await dm.trigger('touchstart')
      vi.advanceTimersByTime(500)
      await flushPromises()
      await wrapper.findAll('button').find((b) => b.text().includes('取消标注'))!.trigger('click')
      await flushPromises()
      expect(wrapper.text()).not.toContain('已标注')

      // 复制
      await dm.trigger('touchstart')
      vi.advanceTimersByTime(500)
      await flushPromises()
      await wrapper.findAll('button').find((b) => b.text().includes('复制文本'))!.trigger('click')
      await flushPromises()
      expect(writeText).toHaveBeenCalledWith('你推开酒馆的门。莉亚在角落里朝你举杯。')
    } finally {
      vi.useRealTimers()
    }
  })

  it('长按菜单「听这句」调用 TTS 合成', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = await mountView()
      await wrapper.findAll('.t-msg')[0]!.trigger('touchstart')
      vi.advanceTimersByTime(500)
      await flushPromises()
      await wrapper.findAll('button').find((b) => b.text().includes('听这句'))!.trigger('click')
      await flushPromises()
      expect(mocks.tts).toHaveBeenCalledWith('你推开酒馆的门。莉亚在角落里朝你举杯。')
    } finally {
      vi.useRealTimers()
    }
  })
})
