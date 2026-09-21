/**
 * C 端搜索 API（docs/53 P5）：帖子 / 用户 / 教程（听力素材）三 tab。
 * 后端 = Python `GET /api/v1/search?type=&q=`（只读 Java 侧表；口径见 `app/api/routes/search.py`）。
 */
import { PYTHON_BASE, request } from './client'

export type SearchType = 'posts' | 'users' | 'tutorials'

export interface SearchAuthor {
  nickname: string
  handle: string | null
  tint: string | null
  avatar_url: string | null
}

export interface SearchPostItem {
  id: number
  title: string
  domain: string | null
  kind: string
  author: SearchAuthor
  created_at: string | null
}

export interface SearchUserItem {
  user_id: number
  nickname: string
  handle: string | null
  tint: string | null
  avatar_url: string | null
  cefr_level: string | null
}

export interface SearchTutorialItem {
  id: number
  title: string
  level: number
  duration_s: number | null
  source: string | null
  tags: string[]
}

interface SearchResponse<T> {
  type: SearchType
  items: T[]
}

async function searchBy<T>(type: SearchType, q: string, limit: number): Promise<T[]> {
  const res = await request<SearchResponse<T>>(
    `/api/v1/search?type=${type}&q=${encodeURIComponent(q)}&limit=${limit}`,
    undefined,
    PYTHON_BASE,
  )
  return res.data.items
}

export function searchPosts(q: string, limit = 20): Promise<SearchPostItem[]> {
  return searchBy<SearchPostItem>('posts', q, limit)
}

export function searchUsers(q: string, limit = 20): Promise<SearchUserItem[]> {
  return searchBy<SearchUserItem>('users', q, limit)
}

export function searchTutorials(q: string, limit = 20): Promise<SearchTutorialItem[]> {
  return searchBy<SearchTutorialItem>('tutorials', q, limit)
}
