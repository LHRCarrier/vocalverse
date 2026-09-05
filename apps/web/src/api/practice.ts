/**
 * M2 练习 API 封装（docs/14 §6.2）：会话/回合/报告/场景/答辩。
 * SSE 回合流经 openSseFetch（POST 音频 → 事件流），不走 request() 的 JSON 路径。
 */
import { openSseFetch } from '@/audio/sse'
import type { SseStreamEvent } from '@/audio/sse-types'
import { authHeaders, request } from './client'

export interface ScenarioItem {
  id: number
  title: string
  scene_type: string
  difficulty: number
  description?: string | null
  opening_line?: string | null
  target_corpus?: string | null
  estimated_turns?: number | null
}

export interface SessionCreated {
  id: number
  kind: string
  scenario_id?: number | null
  profile_id?: number | null
  assigned_turns?: number | null
}

export interface ReportPayload {
  id: number
  computed_at?: string
  metrics: {
    summary?: string
    coverage?: { covered: string[]; needs_fix: string[]; to_practice: string[]; coverage_count: number }
    suggestions?: string[]
    attempts?: Array<Record<string, unknown>>
    [key: string]: unknown
  }
}

export interface DefenseProfileView {
  id: number
  title: string
  status: 'generating' | 'ready' | 'active' | 'failed' | 'deleted'
  question_count: number
  bank_version: number
  knowledge_bank: Record<string, unknown>
}

export async function fetchScenarios(): Promise<ScenarioItem[]> {
  const resp = await request<ScenarioItem[]>('/api/v1/scenarios')
  return resp.data
}

/** 自由对话消息（客户端携带的滚动历史，MVP 无状态，docs/14 §12） */
export interface FreeChatMsg {
  role: 'user' | 'assistant'
  content: string
}

/** 自由对话回合：multipart（audio / text / history JSON）→ SSE 子集事件（docs/14 §12） */
export function streamFreeChat(
  form: FormData,
  onEvent: (e: SseStreamEvent) => void,
  onError: (err: unknown) => void,
  signal?: AbortSignal,
): void {
  openSseFetch(
    '/api/v1/free-chat/turn',
    { method: 'POST', body: form, headers: authHeaders() },
    { onEvent, onError, onClose: () => undefined },
    signal,
  )
}

export async function createSession(payload: {
  kind: 'dialog' | 'defense'
  scenario_id?: number
  profile_id?: number
  difficulty?: number
  turn_limit?: number
}): Promise<SessionCreated> {
  const resp = await request<SessionCreated>('/api/v1/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return resp.data
}

export function streamTurn(
  sessionId: number,
  form: FormData,
  onEvent: (e: SseStreamEvent) => void,
  onError: (err: unknown) => void,
  signal?: AbortSignal,
): void {
  openSseFetch(
    `/api/v1/sessions/${sessionId}/turns`,
    { method: 'POST', body: form, headers: authHeaders() },
    { onEvent, onError, onClose: () => undefined },
    signal,
  )
}

export async function fetchReport(reportId: number): Promise<ReportPayload> {
  const resp = await request<ReportPayload>(`/api/v1/reports/${reportId}`)
  return resp.data
}

export async function fetchDefenseProfile(profileId: number): Promise<DefenseProfileView> {
  const resp = await request<DefenseProfileView>(`/api/v1/defense/profiles/${profileId}`)
  return resp.data
}

export async function createDefenseProfile(payload: Record<string, unknown>) {
  const resp = await request<{ id: number; status: string }>('/api/v1/defense/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return resp.data
}

export async function tts(text: string): Promise<Blob> {
  const form = new FormData()
  form.append('text', text)
  form.append('voice', 'en-US-JennyNeural')
  const resp = await request<{ audio_bytes: string; length: number }>('/api/v1/tts', {
    method: 'POST',
    body: form,
  })
  return new Blob([hexToBytes(resp.data.audio_bytes)], { type: 'audio/mpeg' })
}

function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2)
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16)
  return out
}

export { authHeaders }
