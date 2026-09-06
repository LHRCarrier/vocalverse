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

/** 媒体元数据（后端 media jsonb；字段集对齐 MediaItem——duration 存秒，C-06） */
export interface PostMedia {
  type?: 'image' | 'video' | 'none' | string
  url?: string | null
  coverUrl?: string | null
  durationS?: number | null
  width?: number | null
  height?: number | null
  size?: number | null
  mimeType?: string | null
}

export interface AuthorView {
  id: number
  nickname: string
  handle: string | null
  tint: string | null
  level: string
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
