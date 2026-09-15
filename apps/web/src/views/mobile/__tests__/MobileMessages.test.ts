import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileChatView from '@/views/mobile/MobileChatView.vue'
import MobileMessagesView from '@/views/mobile/MobileMessagesView.vue'

import type { ConversationView } from '@/types/community'

/**
 * 私信两页（真实 IM · docs/49 · 2026-09-10 重写）
 *
 * 旧断言对象是 `data/messages-demo.ts` 的演示会话（Kai / Momo / 自动回复轮换），该文件已随
 * 私信真实化删除；本文件改为断言「真实接口渲染 + 发送 + 未读 >0 才显示」。
 */
const mocks = vi.hoisted(() => {
  const now = new Date().toISOString()
  const peer = { id: 2, nickname: 'Teacher Amy', handle: 'amyteach', tint: '#37546e', level: 'L4', avatarUrl: null }
  const conversation = {
    peer,
    lastMessageId: 9,
    lastBody: '先读十分钟',
    lastMine: false,
    lastCreatedAt: now,
    unreadCount: 2,
  }
  return {
    now,
    peer,
    conversation,
    fetchConversations: {} as ReturnType<typeof vi.fn>,
    fetchUnreadTotal: {} as ReturnType<typeof vi.fn>,
    fetchThread: {} as ReturnType<typeof vi.fn>,
    sendMessage: {} as ReturnType<typeof vi.fn>,
    markThreadRead: {} as ReturnType<typeof vi.fn>,
    openMessageStream: {} as ReturnType<typeof vi.fn>,
  }
})

const peer = mocks.peer
const conversation = mocks.conversation as ConversationView

vi.mock('@/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/community')>()
  // 注意：mock 工厂被提升到文件顶部，**不得引用模块级变量**（含 mocks.conversation）——
  // 用工厂内局部数据构造返回值，避免「Cannot access before initialization」
  const ts = new Date().toISOString()
  mocks.fetchConversations = vi.fn().mockResolvedValue([
    {
      peer: { id: 2, nickname: 'Teacher Amy', handle: 'amyteach', tint: '#37546e', level: 'L4', avatarUrl: null },
      lastMessageId: 9,
      lastBody: '先读十分钟',
      lastMine: false,
      lastCreatedAt: ts,
      unreadCount: 2,
    },
  ])
  mocks.fetchUnreadTotal = vi.fn().mockResolvedValue(2)
  mocks.fetchThread = vi.fn().mockResolvedValue({
    items: [
      { id: 8, peerId: 2, body: 'How do you fit shadowing into a busy day?', mine: false, createdAt: ts },
    ],
    nextCursor: null,
    hasMore: false,
  })
  mocks.sendMessage = vi.fn().mockResolvedValue({
    id: 10,
    peerId: 2,
    body: 'See you tomorrow!',
    mine: true,
    createdAt: ts,
  })
  mocks.markThreadRead = vi.fn().mockResolvedValue({ peerId: 2, lastReadId: 8 })
  mocks.openMessageStream = vi.fn()
  return {
    ...actual,
    fetchConversations: mocks.fetchConversations,
    fetchUnreadTotal: mocks.fetchUnreadTotal,
    fetchThread: mocks.fetchThread,
    sendMessage: mocks.sendMessage,
    markThreadRead: mocks.markThreadRead,
    openMessageStream: mocks.openMessageStream,
  }
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/messages', component: MobileMessagesView },
    { path: '/m/messages/:id', component: MobileChatView },
  ],
})

beforeEach(() => {
  setActivePinia(createPinia())
  mocks.fetchConversations.mockClear()
  mocks.fetchThread.mockClear()
  mocks.sendMessage.mockClear()
  mocks.markThreadRead.mockClear()
})

describe('MobileMessagesView（真实会话列表）', () => {
  it('渲染对端昵称 / LV / 最后一条（我发的加「我：」）/ 未读数字；无未读不显示角标', async () => {
    mocks.fetchConversations.mockResolvedValueOnce([
      conversation,
      { ...conversation, peer: { ...peer, id: 3, nickname: 'Emma' }, lastBody: 'ok', lastMine: true, unreadCount: 0 },
    ])
    await router.push('/m/messages')
    await router.isReady()
    const wrapper = mount(MobileMessagesView, { global: { plugins: [router] } })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('Teacher Amy')
    expect(text).toContain('LV4')
    expect(text).toContain('先读十分钟')
    expect(text).toContain('我：ok')
    // 未读数字只在 >0 时出现（Emma 未读 0 → 无角标）
    expect(wrapper.findAll('.u-msg__unread')).toHaveLength(1)
    expect(wrapper.find('.u-msg__unread').text()).toBe('2')
  })

  it('加载失败：显示错误文案而非空态', async () => {
    mocks.fetchConversations.mockRejectedValueOnce(new Error('私信加载失败'))
    await router.push('/m/messages')
    await router.isReady()
    const wrapper = mount(MobileMessagesView, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('私信加载失败')
  })
})

describe('MobileChatView（真实会话）', () => {
  it('渲染历史消息 → 发送后我方气泡上屏（服务端视图替换占位）', async () => {
    await router.push('/m/messages/2')
    await router.isReady()
    const wrapper = mount(MobileChatView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('How do you fit shadowing into a busy day?')
    expect(mocks.fetchThread).toHaveBeenCalledWith(2, null)
    expect(mocks.markThreadRead).toHaveBeenCalledWith(2, 8)
    // 进入会话即建立实时通道（SSE 优先）
    expect(mocks.openMessageStream).toHaveBeenCalled()

    await wrapper.get('input[aria-label="消息内容"]').setValue('See you tomorrow!')
    await wrapper.get('button[aria-label="发送消息"]').trigger('click')
    await flushPromises()

    expect(mocks.sendMessage).toHaveBeenCalledWith(2, 'See you tomorrow!')
    const text = wrapper.text()
    expect(text).toContain('See you tomorrow!')
    expect(wrapper.findAll('.u-chat__row.is-me').length).toBeGreaterThan(0)
  })

  it('非法 peerId：回退会话列表（不发起请求）', async () => {
    mocks.fetchThread.mockClear()
    await router.push('/m/messages/abc')
    await router.isReady()
    mount(MobileChatView, { global: { plugins: [router] } })
    await flushPromises()
    expect(mocks.fetchThread).not.toHaveBeenCalled()
  })
})
