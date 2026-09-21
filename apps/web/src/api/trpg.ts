/**
 * 酒馆（TRPG 跑团）API 封装（docs/52 §4）：剧本/主持台面板/桌骰/SSE 回合。
 *
 * SSE 回合流经 openSseFetch（POST multipart → 事件流），不走 request() 的 JSON 路径；
 * 主持人回复的逐句 TTS 由服务端合成（audio_chunk），前端只负责排队播放。
 */
import { openSseFetch } from '@/audio/sse'
import type { TrpgSseEvent } from '@/audio/trpg-sse-types'

import { authHeaders, request } from './client'

export interface TrpgCampaignItem {
  id: number
  name: string
  last_active_at?: string | null
  create_time?: string | null
}

export interface TrpgFactItem {
  id: number
  key: string
  value: string
  kind: 'state' | 'fact'
  modality: 'fact' | 'claim' | 'rumor'
  speaker?: string | null
  importance: number
  user_touched_at?: string | null
  user_deleted_at?: string | null
  version?: number
}

export interface TrpgTaskItem {
  id: number
  title: string
  status: 'active' | 'done' | 'failed'
  scene?: string | null
  last_mentioned_at?: string | null
}

export interface TrpgClueItem {
  id: number
  title: string
  content?: string | null
  scene?: string | null
  found: boolean
  recovered: boolean
  last_mentioned_at?: string | null
}

export interface TrpgEntityItem {
  kind: string
  name: string
  status: string
  pending: boolean
}

export interface TrpgEventItem {
  id: number
  round: number
  summary: string
  created_at?: string | null
}

export interface TrpgMessageItem {
  id: number
  role: 'user' | 'assistant'
  kind: 'text' | 'system'
  content: string
  payload?: Record<string, unknown> | null
  meta?: Record<string, unknown> | null
  audio_url?: string | null
  created_at?: string | null
}

export interface TrpgVerifyResult {
  dangling: Array<{ type: 'task' | 'clue'; id: number; title: string; last_mentioned_at?: string | null }>
  gap: boolean
  missing: Array<{ type: 'task' | 'clue'; id: number; title: string }>
  patch_text?: string | null
  contradiction: boolean
}

export interface TrpgState {
  campaign: { id: number; name: string; narrative_summary?: string | null }
  messages: TrpgMessageItem[]
  facts: TrpgFactItem[]
  tasks: TrpgTaskItem[]
  clues: TrpgClueItem[]
  entities: TrpgEntityItem[]
  events: TrpgEventItem[]
  scene?: string | null
  snapshot: string
  narrative_summary?: string | null
  verify: TrpgVerifyResult
}

export interface TrpgRollResult {
  text: string
  summary: string
  state: TrpgState
}

export async function fetchCampaigns(): Promise<TrpgCampaignItem[]> {
  const resp = await request<TrpgCampaignItem[]>('/api/v1/trpg/campaigns')
  return resp.data
}

export async function createCampaign(name: string): Promise<{ id: number; name: string }> {
  const resp = await request<{ id: number; name: string }>('/api/v1/trpg/campaigns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  return resp.data
}

export async function fetchCampaignState(campaignId: number): Promise<TrpgState> {
  const resp = await request<TrpgState>(`/api/v1/trpg/campaigns/${campaignId}`)
  return resp.data
}

export async function clearCampaignMessages(campaignId: number): Promise<number> {
  const resp = await request<{ removed: number }>(
    `/api/v1/trpg/campaigns/${campaignId}/messages`,
    { method: 'DELETE' },
  )
  return resp.data.removed
}

/** 回合流（multipart：text / audio 至少其一）→ SSE 事件流 */
export function streamTrpgTurn(
  campaignId: number,
  form: FormData,
  onEvent: (e: TrpgSseEvent) => void,
  onError: (err: unknown) => void,
  onClose: () => void,
  signal?: AbortSignal,
): void {
  openSseFetch(
    `/api/v1/trpg/campaigns/${campaignId}/turns`,
    { method: 'POST', body: form, headers: authHeaders() },
    { onEvent, onError, onClose },
    signal,
  )
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const resp = await request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  return resp.data
}

export function editFact(campaignId: number, key: string, value: string) {
  return post<{ ok: boolean }>(`/api/v1/trpg/campaigns/${campaignId}/facts/edit`, { key, value })
}

export function deleteFact(campaignId: number, key: string) {
  return post<{ ok: boolean }>(`/api/v1/trpg/campaigns/${campaignId}/facts/delete`, { key })
}

export function restoreFact(campaignId: number, key: string, value: string) {
  return post<{ ok: boolean }>(`/api/v1/trpg/campaigns/${campaignId}/facts/restore`, {
    key,
    value,
  })
}

export function createTask(campaignId: number, title: string, scene?: string) {
  return post<{ ok: boolean }>(`/api/v1/trpg/campaigns/${campaignId}/tasks`, { title, scene })
}

export function setTaskStatus(campaignId: number, taskId: number, status: string) {
  return post<{ ok: boolean }>(
    `/api/v1/trpg/campaigns/${campaignId}/tasks/${taskId}/status`,
    { status },
  )
}

export function createClue(campaignId: number, title: string, content?: string, scene?: string) {
  return post<{ ok: boolean }>(`/api/v1/trpg/campaigns/${campaignId}/clues`, {
    title,
    content,
    scene,
  })
}

export function setClueRecovered(campaignId: number, clueId: number, recovered: boolean) {
  return post<{ ok: boolean }>(
    `/api/v1/trpg/campaigns/${campaignId}/clues/${clueId}/recover`,
    { recovered },
  )
}

export function setScene(campaignId: number, scene: string) {
  return post<{ ok: boolean }>(`/api/v1/trpg/campaigns/${campaignId}/scene`, { scene })
}

export function rollDice(campaignId: number, payload: Record<string, unknown>) {
  return post<TrpgRollResult>(`/api/v1/trpg/campaigns/${campaignId}/roll`, payload)
}

export function refreshNarrative(campaignId: number) {
  return post<{ narrative_summary: string }>(
    `/api/v1/trpg/campaigns/${campaignId}/narrative/refresh`,
  )
}
