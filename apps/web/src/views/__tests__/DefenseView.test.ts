import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import DefenseView from '@/views/DefenseView.vue'
import * as practiceApi from '@/api/practice'
import type { SseStreamEvent } from '@/audio/sse-types'

const fake = vi.hoisted(() => ({
  onEvent: null as ((e: SseStreamEvent) => void) | null,
  streamSignal: null as AbortSignal | null,
}))

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
    createDefenseProfile: vi.fn(),
    fetchDefenseProfile: vi.fn(),
    createSession: vi.fn(),
    streamTurn: vi.fn(),
    tts: vi.fn(),
  }
})

vi.mock('@/api/events', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/events')>()
  return { ...actual, track: vi.fn().mockResolvedValue(undefined) }
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/defense', component: DefenseView }],
})

beforeEach(() => {
  fake.onEvent = null
  fake.streamSignal = null
  vi.mocked(practiceApi.createDefenseProfile).mockResolvedValue({ id: 1, status: 'generating' })
  vi.mocked(practiceApi.fetchDefenseProfile).mockResolvedValue({
    id: 1,
    title: 't',
    status: 'active',
    question_count: 5,
    bank_version: 1,
    knowledge_bank: {},
  })
  vi.mocked(practiceApi.createSession).mockResolvedValue({ id: 7, kind: 'defense' })
  vi.mocked(practiceApi.streamTurn).mockImplementation((_sid, _form, onEvent, _onErr, signal) => {
    fake.onEvent = onEvent
    fake.streamSignal = signal ?? null
  })
})

/** 表单默认值可直接提交：生成 → 轮询 → 题库就绪 → 开始答辩（进入 session，streamTurn 已带 signal） */
async function reachSession(wrapper: ReturnType<typeof mount>) {
  await wrapper.findAll('button').find((b) => b.text().includes('生成问题库'))!.trigger('click')
  await vi.advanceTimersByTimeAsync(0) // flush createDefenseProfile
  await vi.advanceTimersByTimeAsync(1500) // poll 触发 → fetchDefenseProfile active
  await vi.advanceTimersByTimeAsync(0)
  await wrapper.findAll('button').find((b) => b.text().includes('开始答辩'))!.trigger('click')
  await vi.advanceTimersByTimeAsync(0) // flush createSession + track + sendServe
}

describe('DefenseView（fe-02 abort + fe-07 定时器清理）', () => {
  it('streamTurn 传入 signal，组件卸载时 abort（修复前：无 signal，连接挂到 90s 超时）', async () => {
    vi.useFakeTimers()
    await router.push('/defense')
    await router.isReady()
    const wrapper = mount(DefenseView, { global: { plugins: [router] } })
    await reachSession(wrapper)

    expect(practiceApi.streamTurn).toHaveBeenCalled()
    expect(fake.streamSignal).toBeTruthy()
    expect(fake.streamSignal!.aborted).toBe(false)

    wrapper.unmount()
    expect(fake.streamSignal!.aborted).toBe(true)
    vi.useRealTimers()
  })

  it('session_end 后卸载：报告跳转定时器被清理，不把用户拽回报告页（修复前：离开仍 1200ms 后 push）', async () => {
    vi.useFakeTimers()
    await router.push('/defense')
    await router.isReady()
    const wrapper = mount(DefenseView, { global: { plugins: [router] } })
    await reachSession(wrapper)

    const pushSpy = vi.spyOn(router, 'push')
    fake.onEvent!({ type: 'session_end', report_id: 9, summary: '完成' } as SseStreamEvent)

    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(2000)
    expect(pushSpy).not.toHaveBeenCalled()
    vi.useRealTimers()
  })
})
