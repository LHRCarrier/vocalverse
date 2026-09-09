/**
 * 社区 API 域模块（Java 8080 · /manage 代理；docs/37 §5）
 *
 * 集中维护展示语义映射（A-03/A-02）：
 * - domain 存储值 news/teaching/overseas ↔ 展示文案；null=你推荐（全量含打卡卡）；
 * - kind 真源 article/video/checkin；
 * - 时间/时长格式化（createdAt ISO → 「x 分钟前」；duration_s → m:ss）。
 * 请求/响应类型来自生成契约（gen:api）→ 边界强转为严格视图类型（服务端保证全量返回）。
 */
import { JAVA_BASE, request } from './client'

import type {
  CoinState,
  CommentPage,
  CommentView,
  CommunityPostView,
  FeedPage,
  FollowRecommend,
  FollowSummary,
  LikeState,
  NotificationItem,
  NotificationsPage,
  ShareState,
} from '@/types/community'
import type {
  RawCommentPage,
  RawCommentView,
  RawFeedPage,
  RawFollowRecommend,
  RawFollowSummary,
  RawNotificationsPage,
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

/** feed（keyset 游标；domain 空 = 全量混排；后端返回 current user liked/coined 态） */
export async function fetchFeed(domain: string | null, cursor: string | null, limit = 10, signal?: AbortSignal) {
  const res = await request<RawFeedPage>(
    `/api/v1/community/posts${qs({ domain: domain ?? '', cursor: cursor ?? '', limit })}`,
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
