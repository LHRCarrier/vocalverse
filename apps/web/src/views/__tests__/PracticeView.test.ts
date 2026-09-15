import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import PracticeView from '@/views/PracticeView.vue'
import * as practiceApi from '@/api/practice'

vi.mock('@/audio/recorder', () => ({
  MIN_RECORD_MS: 1000,
  micErrorMessage: (e: unknown) => String(e),
  VoiceRecorder: class {
    state = 'idle'
    onStateChange?: (state: string) => void
    onStop?: (blob: Blob, mime: string, durationMs: number) => void
    start() {
      this.state = 'recording'
      this.onStateChange?.('recording')
      return Promise.resolve()
    }
    stop() {
      this.state = 'idle'
      this.onStateChange?.('idle')
    }
    cancel() {
      this.state = 'idle'
      this.onStateChange?.('idle')
    }
  },
}))

vi.mock('@/api/practice', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/practice')>()
  return {
    ...actual,
    createSession: vi.fn(),
    fetchScenarios: vi.fn(),
    fetchSessionRestore: vi.fn(),
    streamTurn: vi.fn(),
    tts: vi.fn(),
  }
})

vi.mock('@/api/events', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/events')>()
  return { ...actual, track: vi.fn().mockResolvedValue(undefined) }
})

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, loadAudioBlob: vi.fn().mockResolvedValue(new Blob(['x'])) }
})

vi.mock('@/composables/useP5Wave', () => ({ useP5Wave: vi.fn() }))
vi.mock('@/composables/useBlobAudio', () => ({
  useBlobAudio: () => ({ createUrl: vi.fn(() => 'blob:x'), revokeUrl: vi.fn(), releaseAll: vi.fn() }),
}))
vi.mock('@/composables/useTurnTimers', () => ({
  useTurnTimers: () => ({
    setTimer: vi.fn(),
    clearAll: vi.fn(),
    clearTimer: vi.fn(),
  }),
}))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/practice/:sceneId', component: PracticeView }],
})

const RESTORE_ACTIVE = {
  id: 42,
  kind: 'dialog',
  status: 'active' as const,
  assigned_turns: 8,
  state: 'awaiting_user',
  current_turn: 1,
  next_seq: 4,
  next_expected_turn: 1,
  report_id: null,
  messages: [
    { seq: 1, role: 'assistant' as const, content: 'Hi! Welcome.' },
    { seq: 2, role: 'user' as const, content: "I'd like a coffee, please." },
    { seq: 3, role: 'assistant' as const, content: 'Here you go!' },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(practiceApi.fetchScenarios).mockResolvedValue([
    { id: 1, title: 'cafe', scene_type: 'cafe', difficulty: 1, opening_line: 'Hi! Welcome.' },
  ])
  vi.mocked(practiceApi.createSession).mockResolvedValue({ id: 7, kind: 'dialog', assigned_turns: 8 })
})

describe('PracticeView（R-13 断线重连：?session=<id> 走恢复而非新建）', () => {
  it('恢复路径：fetchSessionRestore 被调、既有消息渲染、轮次用服务端权威值（修复前：忽略 query 直接 createSession）', async () => {
    vi.mocked(practiceApi.fetchSessionRestore).mockResolvedValue(RESTORE_ACTIVE)
    await router.push('/practice/1?session=42')
    await router.isReady()
    const wrapper = mount(PracticeView, { global: { plugins: [router] } })
    await flushPromises()
    await flushPromises()

    expect(practiceApi.fetchSessionRestore).toHaveBeenCalledWith(42)
    expect(practiceApi.createSession).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Hi! Welcome.')
    expect(wrapper.text()).toContain("I'd like a coffee, please.")
    expect(wrapper.text()).toContain('Here you go!')
    expect(wrapper.text()).toContain('第 1 / 8 轮')
  })

  it('已完成会话恢复：直接跳转报告页（修复前：无恢复逻辑，仍在练习页）', async () => {
    vi.mocked(practiceApi.fetchSessionRestore).mockResolvedValue({
      ...RESTORE_ACTIVE,
      status: 'completed',
      state: 'completed',
      report_id: 9,
    })
    const pushSpy = vi.spyOn(router, 'push')
    await router.push('/practice/1?session=42')
    await router.isReady()
    const wrapper = mount(PracticeView, { global: { plugins: [router] } })
    await flushPromises()
    await flushPromises()

    expect(pushSpy).toHaveBeenCalledWith('/report/9')
    expect(wrapper.text()).not.toContain('第 1 / 8 轮')
  })

  it('无 ?session：保持既有新建路径（createSession + 开场）', async () => {
    await router.push('/practice/1')
    await router.isReady()
    const wrapper = mount(PracticeView, { global: { plugins: [router] } })
    await flushPromises()
    await flushPromises()

    expect(practiceApi.createSession).toHaveBeenCalled()
    expect(practiceApi.fetchSessionRestore).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('cafe')
  })
})
