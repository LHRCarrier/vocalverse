/**
 * 社区 API 域模块（Java 8080 · /manage 代理；docs/37 §5）
 *
 * 集中维护展示语义映射（A-03/A-02）：
 * - domain 存储值 news/teaching/overseas ↔ 展示文案；null=你推荐（全量含打卡卡）；
 * - kind 真源 article/video/checkin；
 * - 时间/时长格式化（createdAt ISO → 「x 分钟前」；duration_s → m:ss）。
 * 请求/响应类型来自生成契约（gen:api）→ 边界强转为严格视图类型（服务端保证全量返回）。
 */
import { JAVA_BASE, authHeaders, request } from './client'

import type {
  CoinState,
  CommentPage,
  CommentView,
  CommunityPostView,
  ConversationView,
  DirectMessageView,
  FeedPage,
  FollowRecommend,
  FollowSummary,
  LikeState,
  MessagePage,
  MessageStreamPayload,
  NotificationItem,
  NotificationsPage,
  ReadState,
  ShareState,
} from '@/types/community'
import type {
  RawCommentPage,
  RawCommentView,
  RawConversationView,
  RawDirectMessageView,
  RawFeedPage,
  RawFollowRecommend,
  RawFollowSummary,
  RawMessagePage,
  RawNotificationsPage,
  RawReadState,
  RawCommunityPostView,
} from '@/types/community'

export const DOMAIN_LABELS: Record<string, string> = {
  news: '新闻稿',
  teaching: '教学分享',
  overseas: '海外生活',
}

export const KIND_LABELS: Record<string, string> = {
  article: '图文',
  video: '视频',
  checkin: '打卡',
}

export const COMMUNITY_TABS: { id: string | null; label: string }[] = [
  { id: null, label: '为你推荐' },
  { id: 'news', label: '新闻稿' },
  { id: 'teaching', label: '教学分享' },
  { id: 'overseas', label: '海外生活' },
]

function qs(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') query.set(k, String(v))
  }
  const s = query.toString()
  return s ? `?${s}` : ''
}

/* 服务端保证全量字段 → 边缘强转（docs：契约字段收敛为严格视图，避免全 optional 噪音） */
const asPost = (raw: RawCommunityPostView): CommunityPostView => raw as unknown as CommunityPostView
const asPostPage = (raw: RawFeedPage): FeedPage => ({
  items: (raw.items ?? []).map(asPost),
  nextCursor: raw.nextCursor ?? null,
  hasMore: raw.hasMore ?? false,
})
const asComment = (raw: RawCommentView): CommentView => raw as unknown as CommentView
const asCommentPage = (raw: RawCommentPage): CommentPage => ({
  items: (raw.items ?? []).map(asComment),
  nextCursor: raw.nextCursor ?? null,
  hasMore: raw.hasMore ?? false,
})

/** feed（keyset 游标；domain 空 = 全量混排；mine=true = 只看本人发帖；后端回带 liked/coined 态） */
export async function fetchFeed(
  domain: string | null,
  cursor: string | null,
  limit = 10,
  signal?: AbortSignal,
  mine = false,
) {
  const res = await request<RawFeedPage>(
    `/api/v1/community/posts${qs({
      domain: domain ?? '',
      cursor: cursor ?? '',
      limit,
      mine: mine ? 'true' : '',
    })}`,
    signal ? { signal } : undefined,
    JAVA_BASE,
  )
  return asPostPage(res.data)
}

export async function fetchPost(id: number) {
  const res = await request<RawCommunityPostView>(`/api/v1/community/posts/${id}`, undefined, JAVA_BASE)
  return asPost(res.data)
}

export interface CreatePostInput {
  title?: string
  body: string
  kind: 'article' | 'video'
  domain: string
  /** 媒体引用（社区 S3 · docs/47 §4.3）；纯文本帖不传 */
  media?: PostMediaInput | null
}

/** 发帖 media 载荷（与后端 MediaRefValidator 同形状） */
export interface PostMediaInput {
  type: 'image' | 'video'
  items: Array<{
    id?: string
    url: string
    width?: number | null
    height?: number | null
    size?: number | null
    mimeType?: string | null
  }>
  coverUrl?: string | null
  durationS?: number | null
}

export async function createPost(body: CreatePostInput) {
  const res = await request<RawCommunityPostView>(
    '/api/v1/community/posts',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
    JAVA_BASE,
  )
  return asPost(res.data)
}

export function deletePost(id: number) {
  return request<null>(`/api/v1/community/posts/${id}`, { method: 'DELETE' }, JAVA_BASE)
}

export async function fetchComments(postId: number, cursor: string | null, limit = 10) {
  const res = await request<RawCommentPage>(
    `/api/v1/community/posts/${postId}/comments${qs({ cursor: cursor ?? '', limit })}`,
    undefined,
    JAVA_BASE,
  )
  return asCommentPage(res.data)
}

export async function addComment(postId: number, body: string) {
  const res = await request<RawCommentView>(
    `/api/v1/community/posts/${postId}/comments`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ body }) },
    JAVA_BASE,
  )
  return asComment(res.data)
}

export function likePost(id: number, on: boolean) {
  return request<LikeState>(`/api/v1/community/posts/${id}/likes`, { method: on ? 'PUT' : 'DELETE' }, JAVA_BASE)
}

/** 支持（原投币）：不可取消、一人一帖一次、幂等 */
export function coinPost(id: number) {
  return request<CoinState>(`/api/v1/community/posts/${id}/coins`, { method: 'PUT' }, JAVA_BASE)
}

export function sharePost(id: number) {
  return request<ShareState>(`/api/v1/community/posts/${id}/shares`, { method: 'POST' }, JAVA_BASE)
}

/* ---------------- S2：关注 / 通知（docs/41） ---------------- */

export function followUser(targetUserId: number) {
  return request<null>(`/api/v1/community/follows/${targetUserId}`, { method: 'PUT' }, JAVA_BASE)
}

export function unfollowUser(targetUserId: number) {
  return request<null>(`/api/v1/community/follows/${targetUserId}`, { method: 'DELETE' }, JAVA_BASE)
}

export async function fetchFollows(): Promise<FollowSummary[]> {
  const res = await request<RawFollowSummary[]>(`/api/v1/community/follows`, undefined, JAVA_BASE)
  return (res.data ?? []).map((r) => r as unknown as FollowSummary)
}

export async function fetchFollowRecommendations(): Promise<FollowRecommend[]> {
  const res = await request<RawFollowRecommend[]>(`/api/v1/community/follows/recommendations`, undefined, JAVA_BASE)
  return (res.data ?? []).map((r) => r as unknown as FollowRecommend)
}

export async function fetchFollowingFeed(cursor: string | null, limit = 10) {
  const res = await request<RawFeedPage>(
    `/api/v1/community/following-feed${qs({ cursor: cursor ?? '', limit })}`,
    undefined,
    JAVA_BASE,
  )
  return asPostPage(res.data)
}

export async function fetchNotifications(cursor: string | null, limit = 10): Promise<NotificationsPage> {
  const res = await request<RawNotificationsPage>(
    `/api/v1/community/notifications${qs({ cursor: cursor ?? '', limit })}`,
    undefined,
    JAVA_BASE,
  )
  return {
    items: (res.data.items ?? []).map((n) => n as unknown as NotificationItem),
    nextCursor: res.data.nextCursor ?? null,
    hasMore: res.data.hasMore ?? false,
  }
}

/* ---------------- 私信 IM（docs/49 §2 · 2026-09-10） ---------------- */

/** 会话列表（对端 + 最后一条 + 我未读）。 */
export async function fetchConversations(limit = 50): Promise<ConversationView[]> {
  const res = await request<RawConversationView[]>(
    `/api/v1/community/messages/conversations${qs({ limit })}`,
    undefined,
    JAVA_BASE,
  )
  return (res.data ?? []).map((r) => r as unknown as ConversationView)
}

/** 未读合计（会话列表页脚 / SSE 校正口径）。 */
export async function fetchUnreadTotal(): Promise<number> {
  const res = await request<number>(`/api/v1/community/messages/unread`, undefined, JAVA_BASE)
  return res.data ?? 0
}

/** 会话消息（keyset 倒序；cursor = 上一页最后一条 id）。 */
export async function fetchThread(
  peerId: number,
  cursor: number | null,
  limit = 20,
  signal?: AbortSignal,
): Promise<MessagePage> {
  const res = await request<RawMessagePage>(
    `/api/v1/community/messages/${peerId}${qs({ cursor: cursor ?? '', limit })}`,
    signal ? { signal } : undefined,
    JAVA_BASE,
  )
  const raw = res.data
  return {
    items: (raw.items ?? []) as unknown as DirectMessageView[],
    nextCursor: raw.nextCursor ?? null,
    hasMore: raw.hasMore ?? false,
  }
}

/** 发送私信（服务端返回权威视图，前端以它替换乐观占位）。 */
export async function sendMessage(peerId: number, body: string): Promise<DirectMessageView> {
  const res = await request<RawDirectMessageView>(
    `/api/v1/community/messages/${peerId}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ body }) },
    JAVA_BASE,
  )
  return res.data as unknown as DirectMessageView
}

/**
 * 已读上报：`upTo` = 本次已渲染的最后一条**对端**消息 id（docs/49 §4.1）。
 *
 * <p>不用请求时刻——时间戳水位会跨过并发提交中尚未渲染的消息，造成永久漏未读（§4.3 B2）。
 */
export async function markThreadRead(peerId: number, upTo: number): Promise<ReadState> {
  const res = await request<RawReadState>(
    `/api/v1/community/messages/${peerId}/read`,
    { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ upTo }) },
    JAVA_BASE,
  )
  return res.data as unknown as ReadState
}

/**
 * 私信 SSE 长连（docs/49 §3.1）——**Java 侧首条流式端点**，与 `audio/sse.ts` 的 Python 音频流不是同一条通道：
 *
 * - `sse.ts` 的 `openSseFetch` 硬绑 `PYTHON_BASE`、只支持 POST+FormData、且丢弃 `id:` 行 → 本函数独立实现
 *   GET + Bearer + `JAVA_BASE`，续传用 `since` 游标（服务端按 `since` 回放断线期间的来信）；
 * - SSE 帧格式：`event:<name>` + `data:<json>`（服务端 `SseEmitter.event()` 默认输出，`data` 后无空格）；
 * - 401 不自动续期（`request()` 才有 authRefresher）：交由调用方降级轮询，重连由上层退避驱动；
 * - 单用户 ≤3 流、全局 ≤500：超限服务端回 `429 + event:error(data:stream-limit)` → `onFail('limit')`。
 */
export interface MessageStreamHandlers {
  /** `event:message`（新消息或断线回放）。 */
  onMessage?: (payload: MessageStreamPayload) => void
  /** `event:open`（建流成功）。 */
  onOpen?: () => void
  /** `event:read`（本账号其他端的已读回执）。 */
  onRead?: (payload: { peerId: number; lastReadId: number }) => void
  /** 流结束/失败：`limit` = 超限（应转轮询）；`error` = 网络/认证失败。 */
  onFail?: (reason: 'limit' | 'error', err?: unknown) => void
}

/** SSE 空闲超时（服务端心跳 25s，取 3× 兜底，同 `SSE_IDLE_TIMEOUT_MS` 口径）。 */
export const MESSAGE_STREAM_IDLE_TIMEOUT_MS = 75_000

export function openMessageStream(
  since: number | null,
  handlers: MessageStreamHandlers,
  signal: AbortSignal,
): void {
  const url = `${JAVA_BASE}/api/v1/community/messages/stream${qs({ since: since ?? '' })}`
  const headers: HeadersInit = {
    Accept: 'text/event-stream',
    ...(authHeaders() as Record<string, string>),
  }
  let failed = false
  const fail = (reason: 'limit' | 'error', err?: unknown) => {
    if (failed) return
    failed = true
    handlers.onFail?.(reason, err)
  }

  fetch(url, { method: 'GET', headers, signal })
    .then(async (resp) => {
      if (!resp.ok || !resp.body) {
        // 超限：429 + event:error(data:stream-limit)（同步响应体）
        const text = await resp.text().catch(() => '')
        fail(resp.status === 429 || text.includes('stream-limit') ? 'limit' : 'error')
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let idx: number
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
          const block = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          let eventName = 'message'
          const dataLines: string[] = []
          for (const line of block.split('\n')) {
            if (line.startsWith('event:')) eventName = line.slice(6).trim()
            else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
          }
          if (!dataLines.length) continue // 注释帧（`:ping`）
          let payload: unknown
          try {
            payload = JSON.parse(dataLines.join('\n'))
          } catch {
            continue // 坏块容错
          }
          if (eventName === 'open') handlers.onOpen?.()
          else if (eventName === 'message') handlers.onMessage?.(payload as MessageStreamPayload)
          else if (eventName === 'read') handlers.onRead?.(payload as { peerId: number; lastReadId: number })
          else if (eventName === 'error') fail('limit')
        }
      }
      fail('error') // 流被服务端/网络关闭：交由上层重连或降级
    })
    .catch((err) => fail('error', err))
}

/* ---------------- 展示语义工具 ---------------- */

export function domainLabel(domain: string | null): string {
  return domain ? (DOMAIN_LABELS[domain] ?? domain) : '打卡'
}

export function authorDisplay(handle: string | null): string {
  return handle ? `@${handle}` : ''
}

export function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const h = Math.floor(min / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  if (d === 1) return '昨天'
  const dt = new Date(iso)
  return `${dt.getMonth() + 1} 月 ${dt.getDate()} 日`
}

/** 秒 → m:ss（媒体元数据 duration_s 展示串，C-06） */
export function formatDuration(durationS: number | null | undefined): string {
  if (durationS == null) return ''
  const m = Math.floor(durationS / 60)
  const s = durationS % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

/** 千位缩写：328→328 / 1240→1.2k（X 式浅计数） */
export function fmtCount(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}
