/**
 * 私信 store（docs/49 §2/§4 · 2026-09-10）
 *
 * 数据源：Java `/manage/api/v1/community/messages/*`（真实 IM）。
 * 关键口径：
 * - **未读真源在服务端**（会话级水位 `last_read_id`，docs/49 §1.2）；本地只做展示与乐观回滚，
 *   服务端返回的 `unreadCount`/`ReadState` 一律覆盖本地值（不做本地求和）；
 * - **已读上报用 `upTo` = 本地已渲染的最后一条对端消息 id**，不用请求时刻（§4.3 B2 防漏未读）；
 * - **实时通道**：SSE 长连优先（§3.1），建流失败/超限/断线 → 自动降级轮询（会话页 3s、列表 10s，
 *   隐藏或离开即停）；两条通道按消息 id 去重，避免重复渲染。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  fetchConversations,
  fetchThread,
  fetchUnreadTotal,
  markThreadRead,
  openMessageStream,
  sendMessage,
} from '@/api/community'
import { useUiStore } from '@/stores/ui'

import type { ConversationView, DirectMessageView, MessageStreamPayload } from '@/types/community'

/** 单会话本地消息上限（防长会话 DOM/内存无界增长；更早历史按需向上翻页）。 */
const THREAD_CAP = 300
/** 降级轮询间隔（docs/49 §3.1）：会话页 3s；列表 10s（列表只在通知中心可见时轮询）。 */
const POLL_THREAD_MS = 3_000
const POLL_LIST_MS = 10_000

export const useMessagesStore = defineStore('messages', () => {
  const conversations = ref<ConversationView[]>([])
  const unreadTotal = ref(0)
  const loadingList = ref(false)
  const listError = ref('')

  const threadPeerId = ref<number | null>(null)
  const thread = ref<DirectMessageView[]>([])
  const threadLoading = ref(false)
  const threadHasMore = ref(false)
  const threadCursor = ref<number | null>(null)
  const threadError = ref('')

  /** 实时通道状态：'idle' | 'live'（SSE 已连）| 'polling'（降级轮询）。 */
  const streamMode = ref<'idle' | 'live' | 'polling'>('idle')

  const ui = useUiStore()

  let streamAbort: AbortController | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  /** SSE 已投递的消息 id（防「SSE + 轮询/回放」双通道重复渲染）。 */
  const seenIds = new Set<number>()

  const sortedThread = computed(() =>
    [...thread.value].sort((a, b) => a.id - b.id),
  )
  const lastIncomingId = computed(() => {
    const incoming = thread.value.filter((m) => !m.mine)
    return incoming.length ? incoming[incoming.length - 1].id : 0
  })

  function noteIds(items: DirectMessageView[]) {
    for (const m of items) seenIds.add(m.id)
  }

  /** 合并新消息（按 id 去重 + 升序插入 + 上限裁剪）。返回是否真的新增。 */
  function mergeMessages(items: DirectMessageView[]): boolean {
    let added = false
    for (const m of items) {
      if (seenIds.has(m.id)) continue
      seenIds.add(m.id)
      thread.value.push(m)
      added = true
    }
    if (added) {
      thread.value.sort((a, b) => a.id - b.id)
      if (thread.value.length > THREAD_CAP) {
        thread.value = thread.value.slice(thread.value.length - THREAD_CAP)
      }
    }
    return added
  }

  // ------------------------------------------------------------------ 会话列表

  async function loadConversations() {
    loadingList.value = true
    listError.value = ''
    try {
      conversations.value = await fetchConversations()
      unreadTotal.value = await fetchUnreadTotal()
    } catch (e) {
      listError.value = e instanceof Error ? e.message : '私信加载失败'
    } finally {
      loadingList.value = false
    }
  }

  // ------------------------------------------------------------------ 会话消息

  /** 打开会话：拉最新一页（降序 → 本地升序展示），同步 seenIds。 */
  async function openThread(peerId: number) {
    threadPeerId.value = peerId
    thread.value = []
    seenIds.clear()
    threadCursor.value = null
    threadHasMore.value = false
    threadError.value = ''
    threadLoading.value = true
    try {
      const page = await fetchThread(peerId, null)
      noteIds(page.items)
      thread.value = [...page.items].sort((a, b) => a.id - b.id)
      threadCursor.value = page.nextCursor ?? null
      threadHasMore.value = page.hasMore ?? false
    } catch (e) {
      // 便于联调定位（页面另有可见错误态）；本仓未启用 no-console 规则，无需 disable 指令
      console.error('[messages] openThread failed', e)
      threadError.value = e instanceof Error ? e.message : '会话加载失败'
    } finally {
      threadLoading.value = false
    }
  }

  /** 向上翻页（更早的历史）。 */
  async function loadMoreThread() {
    if (threadPeerId.value == null || !threadHasMore.value || threadLoading.value) return
    threadLoading.value = true
    try {
      const page = await fetchThread(threadPeerId.value, threadCursor.value)
      noteIds(page.items)
      thread.value = [...page.items, ...thread.value].sort((a, b) => a.id - b.id)
      threadCursor.value = page.nextCursor
      threadHasMore.value = page.hasMore
    } catch (e) {
      threadError.value = e instanceof Error ? e.message : '加载更多失败'
    } finally {
      threadLoading.value = false
    }
  }

  /**
   * 发送：乐观插入（负 id 占位）→ 成功替换为服务端视图 → 失败回滚 + toast。
   *
   * <p>回滚按「占位 id」定位删除，避免误删并发的其他消息。
   */
  async function send(peerId: number, body: string): Promise<boolean> {
    const text = body.trim()
    if (!text) return false
    const placeholderId = -Date.now()
    const placeholder: DirectMessageView = {
      id: placeholderId,
      peerId,
      body: text,
      mine: true,
      createdAt: new Date().toISOString(),
    }
    thread.value = [...thread.value, placeholder]
    try {
      const saved = await sendMessage(peerId, text)
      thread.value = thread.value.filter((m) => m.id !== placeholderId)
      // 注意：**不要**先 noteIds([saved]) 再 mergeMessages——seenIds 会先登记该 id，
      // 合并时被判为重复而不落进消息流（占位删了、真消息没进 → 气泡消失，2026-09-10 实测踩坑）
      mergeMessages([saved])
      void loadConversations()
      return true
    } catch (e) {
      thread.value = thread.value.filter((m) => m.id !== placeholderId)
      ui.showToast(e instanceof Error ? e.message : '发送失败')
      return false
    }
  }

  /** 已读上报（幂等；服务端水位单调，前端不本地清零，回读服务端结果对齐列表）。 */
  async function markRead(peerId = threadPeerId.value) {
    if (peerId == null) return
    const upTo = lastIncomingId.value
    if (!upTo) return
    try {
      await markThreadRead(peerId, upTo)
      const row = conversations.value.find((c) => c.peer.id === peerId)
      if (row && row.unreadCount > 0) {
        unreadTotal.value = Math.max(0, unreadTotal.value - row.unreadCount)
        row.unreadCount = 0
      }
    } catch {
      // 已读上报失败不阻塞阅读（下次进页/新消息会重试）
    }
  }

  // ------------------------------------------------------------------ 实时通道

  /** 首帧 `since` = 本地已见的最大消息 id（服务端据此回放断线期间的来信）。 */
  function sinceCursor(): number | null {
    let max = 0
    for (const id of seenIds) {
      if (id > max) max = id
    }
    return max > 0 ? max : null
  }

  function applyIncoming(payload: MessageStreamPayload) {
    const msg = payload.message
    if (seenIds.has(msg.id)) return
    // 只有当前打开的会话才插入消息流；其他会话只更新列表未读（避免串会话）
    if (threadPeerId.value != null && msg.peerId === threadPeerId.value) {
      mergeMessages([msg])
      void markRead(msg.peerId)
    }
    bumpConversation(msg)
  }

  /** 列表增量：更新对应会话的最后一条与未读（未读以服务端回带的 per-peer 计数为准）。 */
  function bumpConversation(msg: DirectMessageView) {
    const row = conversations.value.find((c) => c.peer.id === msg.peerId)
    if (row) {
      row.lastMessageId = msg.id
      row.lastBody = msg.body
      row.lastMine = msg.mine
      row.lastCreatedAt = msg.createdAt
      row.unreadCount = msg.mine ? row.unreadCount : row.unreadCount + 1
      conversations.value = [...conversations.value].sort((a, b) => b.lastMessageId - a.lastMessageId)
      unreadTotal.value += 1
    } else {
      // 新会话（此前无往来）：整表重拉（低频，一次请求换正确性）
      void loadConversations()
    }
  }

  function stopStream() {
    streamAbort?.abort()
    streamAbort = null
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    if (streamMode.value !== 'idle') streamMode.value = 'idle'
  }

  /** 降级轮询：会话页 3s 拉当前会话（仅新消息），列表 10s 拉会话行。 */
  function startPolling() {
    if (pollTimer) return
    streamMode.value = 'polling'
    pollTimer = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return // 隐藏即暂停（省电/省请求）
      if (threadPeerId.value != null) {
        const peer = threadPeerId.value
        void fetchThread(peer, null)
          .then((page) => {
            const fresh = page.items.filter((m) => !seenIds.has(m.id))
            if (!fresh.length) return
            noteIds(fresh)
            mergeMessages(fresh)
            void markRead(peer)
            void loadConversations()
          })
          .catch(() => undefined)
      } else {
        void loadConversations()
      }
    }, threadPeerId.value != null ? POLL_THREAD_MS : POLL_LIST_MS)
  }

  /** 建立实时通道（SSE 优先；失败/超限自动降级轮询）。重复调用幂等。 */
  function startStream() {
    if (streamMode.value !== 'idle') return
    streamAbort?.abort()
    const ac = new AbortController()
    streamAbort = ac
    let opened = false
    openMessageStream(
      sinceCursor(),
      {
        onOpen: () => {
          opened = true
          streamMode.value = 'live'
        },
        onMessage: (payload) => applyIncoming(payload),
        onRead: () => {
          // 本账号其他端已读：轻量对齐未读（一次列表刷新换一致性）
          void loadConversations()
        },
        onFail: () => {
          if (ac.signal.aborted) return // 主动关闭不算失败
          if (!opened) streamMode.value = 'idle'
          streamAbort = null
          startPolling()
        },
      },
      ac.signal,
    )
  }

  /** 离开页面：停流 + 结束会话上下文（未读留给服务端水位口径）。 */
  function closeThread() {
    void markRead()
    threadPeerId.value = null
    stopStream()
  }

  return {
    // state
    conversations,
    unreadTotal,
    loadingList,
    listError,
    threadPeerId,
    thread,
    threadLoading,
    threadHasMore,
    threadCursor,
    threadError,
    streamMode,
    // getters
    sortedThread,
    lastIncomingId,
    // actions
    loadConversations,
    openThread,
    loadMoreThread,
    send,
    markRead,
    startStream,
    stopStream,
    closeThread,
  }
})
