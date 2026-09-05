/**
 * 入学测试 API 封装（docs/06 §9.2 · C1 两维 / C5 可跳过+2题 / C8 复测 / C9 对账）。
 * 契约 DTO：真实子集由 openapi-typescript 生成（python-api.d.ts），但 placement 各端点响应
 * 为泛型 Envelope（非组件 schema → unknown），故在此以本地 interface 显式声明。
 */
import { request } from './client'

export interface PlacementQuestion {
  id: number
  kind: 'read' | 'qa'
  prompt: string
  reference_answer?: string | null
}

export interface PlacementStatus {
  has_completed: boolean
  completed_count: number
  current_level?: string | null
  last_completed_at?: string | null
  can_retest: boolean
  cooldown_remaining_days: number
}

export interface ScoreItemResult {
  placement_id: number
  attempt_id: number
  transcript: string
  pron?: number | null
  flu?: number | null
  completeness?: number | null
  gram?: number | null
  relevance?: string | null
}

export interface PlacementFinal {
  placement_id: number
  level: string
  total_score: number
  pron?: number | null
  flu?: number | null
  gram?: number | null
}

export interface RetestStart {
  placement_id: number
  exam_revision: number
  questions: PlacementQuestion[]
  can_start: boolean
}

export interface SkipResult {
  placement_id: number
  level: string
  skipped: boolean
}

export async function fetchPlacementQuestions(): Promise<PlacementQuestion[]> {
  const r = await request<PlacementQuestion[]>('/api/v1/placement/questions')
  return r.data
}

export async function fetchPlacementStatus(): Promise<PlacementStatus> {
  const r = await request<PlacementStatus>('/api/v1/placement/status')
  return r.data
}

export async function startRetest(): Promise<RetestStart> {
  const r = await request<RetestStart>('/api/v1/placement/retest', { method: 'POST' })
  return r.data
}

export async function skipPlacement(): Promise<SkipResult> {
  const r = await request<SkipResult>('/api/v1/placement/skip', { method: 'POST' })
  return r.data
}

export async function scorePlacementItem(itemId: number, blob: Blob): Promise<ScoreItemResult> {
  const form = new FormData()
  form.append('audio', blob, 'recording.webm')
  const r = await request<ScoreItemResult>(`/api/v1/placement/items/${itemId}/audio`, {
    method: 'POST',
    body: form,
  })
  return r.data
}

export async function finalizePlacement(attempts: number[]): Promise<PlacementFinal> {
  const r = await request<PlacementFinal>('/api/v1/placement/finalize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attempts }),
  })
  return r.data
}
