/**
 * 社区类型（M2.5 演示帧 → M3 真实流复用；docs/34 §3、§7.2）
 * M3 真实流：sessions/attempts JOIN 派生 + post_likes（docs/10 注记），字段届时对齐接口。
 */
export type CommunityDomain = '新闻稿' | '教学分享' | '海外生活'

export type CommunityTab = '为你推荐' | CommunityDomain

export interface PostMedia {
  /** 演示：渐变背景；M3 换真实图片 URL */
  gradient: string
  label: string
}

export interface PostStats {
  like: number
  comment: number
  coin: number
  share: number
}

export interface CommunityPost {
  id: number
  author: string
  handle: string
  level: string
  time: string
  domain: CommunityDomain
  kind: 'post' | 'video'
  title: string
  desc?: string
  media?: PostMedia
  duration?: string
  stats: PostStats
  liked: boolean
  tint: string
}
