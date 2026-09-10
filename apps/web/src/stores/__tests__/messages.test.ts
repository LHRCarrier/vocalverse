import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useMessagesStore } from '@/stores/messages'
import * as communityApi from '@/api/community'

import type { ConversationView, DirectMessageView, MessagePage } from '@/types/community'

vi.mock('@/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/community')>()
  return {
    ...actual,
    fetchConversations: vi.fn(),
    fetchUnreadTotal: vi.fn(),
    fetchThread: vi.fn(),
    sendMessage: vi.fn(),
    markThreadRead: vi.fn(),
    openMessageStream: vi.fn(),
  }
})

const msg = (id: number, peerId: number, body: string, mine: boolean): DirectMessageView => ({
  id,
  peerId,
  body,
  mine,
  createdAt: new Date(2026, 8, 10, 10, 0, id).toISOString(),
})

const peer = (id: number, nickname: string) => ({
  id,
  nickname,
  handle: `u${id}`,
  tint: '#37546e',
  level: 'L3',
  avatarUrl: null,
})

const conversation = (peerId: number, unread: number, lastBody: string): ConversationView => ({
  peer: peer(peerId, `同学${peerId}`),
  lastMessageId: 100 + peerId,
  lastBody,
  lastMine: false,
  lastCreatedAt: new Date(2026, 8, 10, 10, 0, peerId).toISOString(),
  unreadCount: unread,
})

const threadPage = (items: DirectMessageView[], cursor: number | null = null): MessagePage => ({
  items,
  nextCursor: cursor,
  hasMore: cursor != null,
})

describe('messages store（私信 IM · docs/49 §2/§4）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(communityApi.fetchConversations).mockReset()
    vi.mocked(communityApi.fetchUnreadTotal).mockReset()
    vi.mocked(communityApi.fetchThread).mockReset()
    vi.mocked(communityApi.sendMessage).mockReset()
    vi.mocked(communityApi.markThreadRead).mockReset()
    vi.mocked(communityApi.openMessageStream).mockReset()
  })

  it('会话列表：对端 + 最后一条 + 服务端未读（不做本地求和）', async () => {
    vi.mocked(communityApi.fetchConversations).mockResolvedValue([
      conversation(2, 3, 'hi A'),
      conversation(3, 0, 'hello'),
    ])
    vi.mocked(communityApi.fetchUnreadTotal).mockResolvedValue(3)

    const store = useMessagesStore()
    await store.loadConversations()

    expect(store.conversations).toHaveLength(2)
    expect(store.conversations[0].peer.nickname).toBe('同学2')
    expect(store.unreadTotal).toBe(3)
    expect(store.listError).toBe('')
  })

  it('打开会话：升序展示 + 记录 nextCursor（keyset 向上翻页）', async () => {
    vi.mocked(communityApi.fetchThread).mockResolvedValue(
      threadPage([msg(12, 2, 'b', false), msg(11, 2, 'a', true)], 11),
    )

    const store = useMessagesStore()
    await store.openThread(2)

    expect(store.sortedThread.map((m) => m.id)).toEqual([11, 12])
    expect(store.threadHasMore).toBe(true)
    expect(store.threadCursor).toBe(11)
  })

  it('发送：乐观上屏 → 服务端视图替换占位（不重复渲染）', async () => {
    vi.mocked(communityApi.fetchThread).mockResolvedValue(threadPage([msg(1, 2, 'hi', false)]))
    vi.mocked(communityApi.sendMessage).mockResolvedValue(msg(2, 2, 'hello', true))
    vi.mocked(communityApi.fetchConversations).mockResolvedValue([conversation(2, 0, 'hello')])
    vi.mocked(communityApi.fetchUnreadTotal).mockResolvedValue(0)

    const store = useMessagesStore()
    await store.openThread(2)
    const ok = await store.send(2, 'hello')

    expect(ok).toBe(true)
    expect(store.sortedThread.map((m) => m.body)).toEqual(['hi', 'hello'])
    expect(store.sortedThread.filter((m) => m.body === 'hello')).toHaveLength(1)
    expect(store.sortedThread.every((m) => m.id > 0)).toBe(true)
  })

  it('发送失败：回滚占位 + toast（修复前失败：占位残留成幽灵消息）', async () => {
    vi.mocked(communityApi.fetchThread).mockResolvedValue(threadPage([msg(1, 2, 'hi', false)]))
    vi.mocked(communityApi.sendMessage).mockRejectedValue(new Error('网络错误'))

    const store = useMessagesStore()
    await store.openThread(2)
    const ok = await store.send(2, 'will-fail')

    expect(ok).toBe(false)
    expect(store.sortedThread.map((m) => m.body)).toEqual(['hi'])
  })

  it('已读上报：upTo = 最后一条对端消息 id（不用请求时刻）', async () => {
    vi.mocked(communityApi.fetchThread).mockResolvedValue(
      threadPage([msg(1, 2, 'theirs-1', false), msg(2, 2, 'mine', true), msg(3, 2, 'theirs-2', false)]),
    )
    vi.mocked(communityApi.markThreadRead).mockResolvedValue({ peerId: 2, lastReadId: 3 })
    vi.mocked(communityApi.fetchConversations).mockResolvedValue([conversation(2, 2, 'theirs-2')])
    vi.mocked(communityApi.fetchUnreadTotal).mockResolvedValue(2)

    const store = useMessagesStore()
    await store.loadConversations()
    await store.openThread(2)
    await store.markRead(2)

    expect(communityApi.markThreadRead).toHaveBeenCalledWith(2, 3)
    expect(store.conversations[0].unreadCount).toBe(0)
    expect(store.unreadTotal).toBe(0)
  })

  it('实时增量：当前会话插入 + 未读更新；重复 id 不重复渲染（双通道去重）', async () => {
    vi.mocked(communityApi.fetchThread).mockResolvedValue(threadPage([msg(1, 2, 'hi', false)]))
    vi.mocked(communityApi.markThreadRead).mockResolvedValue({ peerId: 2, lastReadId: 5 })
    vi.mocked(communityApi.fetchConversations).mockResolvedValue([conversation(2, 1, 'hi')])
    vi.mocked(communityApi.fetchUnreadTotal).mockResolvedValue(1)

    // 捕获 onMessage 回调，手工投递事件（模拟 SSE 帧）
    type Deliver = (p: { message: DirectMessageView; unreadCount: number }) => void
    const box: { deliver: Deliver | null } = { deliver: null }
    vi.mocked(communityApi.openMessageStream).mockImplementation((_since, handlers) => {
      box.deliver = handlers.onMessage ?? null
      handlers.onOpen?.()
    })

    const store = useMessagesStore()
    await store.loadConversations()
    await store.openThread(2)
    store.startStream()
    expect(store.streamMode).toBe('live')

    expect(box.deliver).not.toBeNull()
    box.deliver?.({ message: msg(5, 2, 'live-msg', false), unreadCount: 1 })
    expect(store.sortedThread.map((m) => m.body)).toEqual(['hi', 'live-msg'])

    // 同一条再次投递（SSE 重连回放与轮询重叠）：不重复
    box.deliver?.({ message: msg(5, 2, 'live-msg', false), unreadCount: 1 })
    expect(store.sortedThread.filter((m) => m.body === 'live-msg')).toHaveLength(1)
  })

  it('实时通道失败：自动降级轮询（streamMode=polling）', async () => {
    vi.mocked(communityApi.fetchConversations).mockResolvedValue([])
    vi.mocked(communityApi.fetchUnreadTotal).mockResolvedValue(0)
    vi.mocked(communityApi.openMessageStream).mockImplementation((_since, handlers) => {
      handlers.onFail?.('limit')
    })

    const store = useMessagesStore()
    store.startStream()

    expect(store.streamMode).toBe('polling')
    store.stopStream()
    expect(store.streamMode).toBe('idle')
  })
})
