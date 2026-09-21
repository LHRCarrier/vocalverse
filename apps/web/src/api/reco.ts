/**
 * 推荐 API（docs/53 P3）：跨类内容推荐（歌/书/酒馆场景卡）。
 *
 * 曝光由**服务端**在返回时落库（`recommend_impression` + `recommend_group_id`，docs/11 Q-B01），
 * 前端只负责用返回的 `recommend_group_id` 上报点击（`recommend_click`）——避免双重计数。
 */
import { PYTHON_BASE, request } from './client'

export interface RecoItem {
  kind: 'song' | 'book' | 'card'
  id: number
  title: string
  subtitle: string
  level: string | null
  score: number
  reason: string
}

export interface RecoItems {
  type: 'items'
  items: RecoItem[]
  level: string
  rule_version: string
  recommend_group_id: string
}

export async function fetchItemsRecommendations(limit = 3, kind?: RecoItem['kind']): Promise<RecoItems> {
  const qs = new URLSearchParams({ type: 'items', limit: String(limit) })
  if (kind) qs.set('kind', kind)
  const res = await request<RecoItems>(
    `/api/v1/recommendations?${qs.toString()}`,
    undefined,
    PYTHON_BASE,
  )
  return res.data
}
