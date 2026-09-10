/**
 * 社区类型（S1 真实流 · 与后端契约对齐 2026-09-06）
 *
 * 契约真源 = `src/api/generated/java-api.d.ts`（由 java-openapi.json 构建期生成，
 * docs/06 §7 codegen 口径）；openapi-typescript 生成的字段全 optional，本文件在
 * `api/community.ts` 边界处**强转为严格视图类型**（服务端保证全量返回，cast 有据可依），
 * 组件层获得非空字段的完整类型安心。
 *
 * - kind 真源：`article | video | checkin`（前端旧 'post' 已废弃，A-02）；
 * - domain 存储值：`news | teaching | overseas`（checkin 为 null，仅「为你推荐」混排，A-03）；
 * - 展示文案映射集中在 `src/api/community.ts`，组件层禁止散落判定。
 */
import type { components } from '@/api/generated/java-api'

/** 后端原始视图（生成契约；字段全 optional） */
export type RawCommunityPostView = components['schemas']['CommunityPostView']
export type RawAuthorView = components['schemas']['AuthorView']
export type RawCommentView = components['schemas']['CommentView']
export type RawFeedPage = components['schemas']['FeedPage']
export type RawCommentPage = components['schemas']['CommentPage']
export type RawFollowSummary = components['schemas']['FollowSummary']
export type RawFollowRecommend = components['schemas']['FollowRecommend']
export type RawNotificationsPage = components['schemas']['NotificationsPage']
/* 私信 IM（docs/49 · 2026-09-10；契约见 java-api.d.ts 的 DirectMessageController 段） */
export type RawDirectMessageView = components['schemas']['DirectMessageView']
export type RawConversationView = components['schemas']['ConversationView']
export type RawMessagePage = components['schemas']['MessagePage']
export type RawReadState = components['schemas']['ReadState']

/**
 * 媒体元数据（后端 media jsonb）。
 *
 * 2026-09-09（社区 S3）扩展为**多图** + 兼容 S1 存量数据：
 * - S1 种子写的是 `{"type":"video","duration_s":240}`（snake_case、无 url）；
 * - S1 真实帖写 `{type,url,coverUrl,durationS}`；
 * - S3 新帖写 `{type,items:[{id,url,width,height,size,mimeType}],coverUrl,durationS}`。
 * `normalizeMedia()` 把三种形状统一成 `items[]` + camelCase，渲染层只认归一后的形状
 * （docs/48 B8：此前前端只读 durationS，种子视频的时长角标一直是空的）。
 */
export interface PostMediaItem {
  id?: string | null
  url: string
  width?: number | null
  height?: number | null
  size?: number | null
  mimeType?: string | null
}

export interface PostMedia {
  type?: 'image' | 'video' | 'none' | string
  url?: string | null
  coverUrl?: string | null
  durationS?: number | null
  width?: number | null
  height?: number | null
  size?: number | null
  mimeType?: string | null
  /** 多图/视频项（S3）；缺省时由 normalizeMedia 从 url 归一 */
  items?: PostMediaItem[]
  /** 原始 snake_case 时长（S1 种子；normalizeMedia 会转成 durationS） */
  duration_s?: number | null
  cover_url?: string | null
}

/** 归一后的媒体（渲染层唯一形状） */
export interface NormalizedMedia {
  kind: 'image' | 'video' | 'none'
  items: PostMediaItem[]
  coverUrl: string | null
  durationS: number | null
}

/** 三种历史形状 → 统一形状（纯函数，供渲染层与单测共用） */
export function normalizeMedia(media: PostMedia | null | undefined, postKind?: string): NormalizedMedia {
  if (!media) {
    return { kind: postKind === 'video' ? 'video' : 'none', items: [], coverUrl: null, durationS: null }
  }
  const rawItems = Array.isArray(media.items) ? media.items : []
  const items: PostMediaItem[] = rawItems
    .filter((i): i is PostMediaItem => !!i && typeof i.url === 'string' && i.url.length > 0)
    .map((i) => ({
      id: i.id ?? null,
      url: i.url,
      width: i.width ?? null,
      height: i.height ?? null,
      size: i.size ?? null,
      mimeType: i.mimeType ?? null,
    }))
  if (items.length === 0 && typeof media.url === 'string' && media.url) {
    items.push({
      id: null,
      url: media.url,
      width: media.width ?? null,
      height: media.height ?? null,
      size: media.size ?? null,
      mimeType: media.mimeType ?? null,
    })
  }
  const kind: NormalizedMedia['kind'] =
    media.type === 'video' || postKind === 'video' ? 'video' : items.length ? 'image' : 'none'
  return {
    kind,
    items,
    coverUrl: media.coverUrl ?? media.cover_url ?? null,
    durationS: media.durationS ?? media.duration_s ?? null,
  }
}

export interface AuthorView {
  id: number
  nickname: string
  handle: string | null
  tint: string | null
  level: string
  /** 真实头像（社区 S3 新增；随 AuthorView 一次带回，零额外请求） */
  avatarUrl?: string | null
}

/** 严格视图类型（服务端保证全量返回；cast 在 api/community.ts 边界） */
export interface CommunityPostView {
  id: number
  author: AuthorView
  kind: 'article' | 'video' | 'checkin'
  domain: string | null
  title: string | null
  body: string | null
  media: PostMedia | null
  createdAt: string
  likeCount: number
  coinCount: number
  commentCount: number
  shareCount: number
  liked: boolean
  coined: boolean
  checkinOverall: number | null
  checkinPracticeCount: number | null
  checkinDate: string | null
}

export interface CommentView {
  id: number
  author: AuthorView
  body: string
  createdAt: string
  replyToNickname: string | null
}

export interface FeedPage {
  items: CommunityPostView[]
  nextCursor: string | null
  hasMore: boolean
}

export interface CommentPage {
  items: CommentView[]
  nextCursor: string | null
  hasMore: boolean
}

export interface LikeState {
  liked: boolean
  likeCount: number
}

export interface CoinState {
  coined: boolean
  coinCount: number
}

export interface ShareState {
  shared: boolean
  shareCount: number
}

/* ---------------- S2：关注 / 通知（docs/41） ---------------- */

export type NotificationType = 'like' | 'coin' | 'share' | 'comment'

export interface FollowSummary {
  author: AuthorView
  followedAt: string
  youFollowBack: boolean
}

export interface FollowRecommend {
  author: AuthorView
  followed: boolean
}

export interface NotificationItem {
  id: string
  type: NotificationType
  postId: number
  postTitle: string
  actorNickname: string
  actorCount: number
  commentBody: string | null
  createdAt: string
}

export interface NotificationsPage {
  items: NotificationItem[]
  nextCursor: string | null
  hasMore: boolean
}

/* ---------------- 私信 IM（docs/49 · 2026-09-10） ---------------- */

/** 单条私信（`mine` = 我发的；`peerId` = 对方 userId，收发两侧都是「对方」）。 */
export interface DirectMessageView {
  id: number
  peerId: number
  body: string
  mine: boolean
  createdAt: string
}

/** 会话列表行（对端 + 最后一条 + 我未读数）。 */
export interface ConversationView {
  peer: AuthorView
  lastMessageId: number
  lastBody: string
  lastMine: boolean
  lastCreatedAt: string
  unreadCount: number
}

/** 会话消息页（keyset 倒序；`nextCursor` = 下一页 beforeId）。 */
export interface MessagePage {
  items: DirectMessageView[]
  nextCursor: number | null
  hasMore: boolean
}

/** 已读上报结果（服务端权威水位）。 */
export interface ReadState {
  peerId: number
  lastReadId: number
}

/** SSE 新消息事件载荷（对端视角：message.peerId = 发送者）。 */
export interface MessageStreamPayload {
  message: DirectMessageView
  unreadCount: number
}
