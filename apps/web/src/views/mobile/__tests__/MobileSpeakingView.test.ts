import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { nextTick } from 'vue'

import MobileSpeakingView from '@/views/mobile/MobileSpeakingView.vue'
import * as practiceApi from '@/api/practice'
import type { SseStreamEvent } from '@/audio/sse-types'

/** vi.mock 工厂外可写状态：捕获 recorder.onStop（模拟录音回调）与 streamTurn 的 onEvent（驱动 SSE 流） */
const fake = vi.hoisted(() => ({
  recorderOnStop: null as ((blob: Blob, mime: string, durationMs: number) => void) | null,
  onEvent: null as ((e: SseStreamEvent) => void) | null,
}))

vi.mock('@/audio/recorder', () => ({
  MIN_RECORD_MS: 1000,
  micErrorMessage: (e: unknown) => String(e),
  VoiceRecorder: class {
    state = 'idle'
    onStateChange?: (state: string) => void
    /** 组件 setup 会赋值 onStop；用 setter 捕获供测试直接触发（等价于用户录音停止） */
    get onStop(): ((blob: Blob, mime: string, durationMs: number) => void) | undefined {
      return undefined
    }
    set onStop(fn: (blob: Blob, mime: string, durationMs: number) => void) {
      fake.recorderOnStop = fn
    }
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
    fetchScenarios: vi.fn(),
    createSession: vi.fn(),
    streamTurn: vi.fn(),
    tts: vi.fn(),
  }
})

// track 走真实 fetch 会等网络拒绝（事件循环层，flushPromises 推不动）→ boot() 卡住：mock 成即时 resolve
vi.mock('@/api/events', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/events')>()
  return { ...actual, track: vi.fn().mockResolvedValue(undefined) }
})

const scenario = {
  id: 1,
  title: '机场值机',
  scene_type: 'airport',
  difficulty: 2,
  opening_line: 'Good morning! Welcome. May I see your passport, please?',
}

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/m/chat/:sceneId?', component: MobileSpeakingView }],
})

beforeEach(() => {
  setActivePinia(createPinia())
  fake.recorderOnStop = null
  fake.onEvent = null
  vi.mocked(practiceApi.fetchScenarios).mockResolvedValue([scenario])
  vi.mocked(practiceApi.createSession).mockResolvedValue({ id: 7, kind: 'dialog', scenario_id: 1, assigned_turns: 4 })
  vi.mocked(practiceApi.tts).mockResolvedValue(new Blob([]))
  vi.mocked(practiceApi.streamTurn).mockImplementation((_sessionId, _form, onEvent) => {
    fake.onEvent = onEvent
  })
})

async function mountView() {
  await router.push('/m/chat/1')
  await router.isReady()
  const wrapper = mount(MobileSpeakingView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

/** 驱动一个完整回合（录音→回合流→turn_end）；question 为首句，delta 为后续流式文本 */
function driveTurn(opening: string, delta: string, turnIndex: number) {
  fake.recorderOnStop!(new Blob(['x']), 'audio/webm', 3000)
  fake.onEvent!({ type: 'turn_start', turn_index: turnIndex, question: opening } as SseStreamEvent)
  fake.onEvent!({ type: 'text_delta', text: delta } as SseStreamEvent)
  fake.onEvent!({ type: 'turn_end', turn_index: turnIndex, score_status: 'ok' } as SseStreamEvent)
}

describe('MobileSpeakingView（场景对话重听按钮）', () => {
  it('每条 AI 话语回合结束即解锁重听喇叭，历史气泡保留（修复前仅开场白有按钮）', async () => {
    const wrapper = await mountView()
    // 开场白进页即 speakable → 1 个喇叭
    expect(wrapper.findAll('.u-replay')).toHaveLength(1)

    // 回合气泡流式进行中：不提前出现按钮（turn_end 才解锁）
    fake.recorderOnStop!(new Blob(['x']), 'audio/webm', 3000)
    await flushPromises()
    expect(fake.onEvent).toBeTruthy()
    fake.onEvent!({ type: 'turn_start', turn_index: 0, question: 'Welcome!' } as SseStreamEvent)
    fake.onEvent!({ type: 'text_delta', text: ' Welcome to the airport.' } as SseStreamEvent)
    await nextTick()
    expect(wrapper.findAll('.u-replay')).toHaveLength(1)

    // 第一轮 turn_end → 本回合气泡解锁，开场白保留 → 2 个喇叭
    fake.onEvent!({ type: 'turn_end', turn_index: 0, score_status: 'ok' } as SseStreamEvent)
    await nextTick()
    expect(wrapper.findAll('.u-replay')).toHaveLength(2)

    // 第二轮 turn_end → 只新增 1 个（共 3 个），历史不丢
    driveTurn('How can I help you?', ' Anything else?', 1)
    await nextTick()
    expect(wrapper.findAll('.u-replay')).toHaveLength(3)
  })

  it('点击历史气泡喇叭：按该句文本 TTS 重播（开场白/回合句均可）', async () => {
    const wrapper = await mountView()
    driveTurn('Welcome!', ' to the airport.', 0)
    await nextTick()

    const buttons = wrapper.findAll('.u-replay')
    expect(buttons).toHaveLength(2)

    // 第一个按钮属于开场白（bubble 0）：重播 = 按该句文本实时合成
    await buttons[0].trigger('click')
    await flushPromises()
    expect(practiceApi.tts).toHaveBeenCalledWith(scenario.opening_line)

    // 第二个按钮属于回合气泡（bubble 1）
    await buttons[1].trigger('click')
    await flushPromises()
    expect(practiceApi.tts).toHaveBeenCalledWith('Welcome! to the airport.')
  })
})
