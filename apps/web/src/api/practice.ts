/**
 * M2 练习 API 封装（docs/14 §6.2）：答辩 / 报告 / 自由对话 / TTS。
 *
 * 2026-09-21 酒馆迁移：英语「场景对话」闭环整体移除（会话创建/回合流/场景列表），
 * 本模块保留答辩（defense）、报告、自由对话与 TTS；TTS 实现已移到 `./tts`
 * （此处 re-export，旧引用零改动）。
 */
import { openSseFetch } from '@/audio/sse'
import type { SseStreamEvent } from '@/audio/sse-types'
import { authHeaders, request } from './client'

export { tts } from './tts'

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
  kind: 'defense'
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

export { authHeaders }
