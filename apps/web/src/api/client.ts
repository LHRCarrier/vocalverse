/**
 * API 客户端 —— 统一 envelope 解析（docs/06 第 7 章：{code, message, data}）
 *
 * - 语音/LLM 热路径：Python 8000（dev 下走 Vite 代理 /api/v1）
 * - 管理端/JWT：Java 8080（dev 下走 /manage 代理）
 *
 * 契约（docs/06 §7，2026-08-31 起）：
 * - Python 侧 DTO 类型 = `src/api/generated/python-api.d.ts`（openapi-typescript 构建期生成，
 *   由 `src/api/specs/python-openapi.json` 驱动 —— 后端改契约后跑 `pnpm gen:api` 重新生成，
 *   typecheck 立即暴露断点，消灭手工同步）。
 * - 契约真源是 Python `/openapi.json`；本文件仅含请求封装与错误语义，不手写 DTO。
 */

import type { components } from './generated/python-api'
import type { components as javaComponents } from './generated/java-api'

/**
 * 生成契约里的 DTO 集合（数据层类型，勿在此手改：
 * 一切以 `pnpm gen:api` 生成文件为准）。
 */
export type ApiSchemas = components['schemas']
export type AsrData = ApiSchemas['ASRResult']
export type ScoreData = ApiSchemas['ScoreResult']
export type TtsData = ApiSchemas['TTSResult']
export type ChatData = ApiSchemas['ChatResult']
/** Java 侧 DTO（/manage，2026-09-01 起也由契约生成；ping 曾裸返回 → 见 docs/06 §7 记录） */
export type PingData = javaComponents['schemas']['PingData']

export interface Envelope<T> {
  code: number
  message: string
  data: T
}

const PYTHON_BASE = import.meta.env.VITE_PYTHON_BASE ?? ''
const JAVA_BASE = import.meta.env.VITE_JAVA_BASE ?? '/manage'

/** 全局访问令牌（由 auth store 写入；request 自动携带）。 */
let authToken: string | null = null

export function setAuthToken(token: string | null): void {
  authToken = token
}

export function getAuthToken(): string | null {
  return authToken
}

export class ApiError extends Error {
  constructor(
    public readonly code: number,
    message: string,
    public readonly httpStatus: number,
  ) {
    super(message)
  }
}

export function authHeaders(): HeadersInit {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {}
}

export async function request<T>(path: string, init?: RequestInit, base = PYTHON_BASE): Promise<Envelope<T>> {
  const headers = { ...(init?.headers ?? {}), ...authHeaders() }
  const resp = await fetch(`${base}${path}`, { ...init, headers })
  const body = (await resp.json()) as Envelope<T>
  if (!resp.ok || body.code !== 0) {
    throw new ApiError(body.code ?? -1, body.message ?? `HTTP ${resp.status}`, resp.status)
  }
  return body
}

export function readyz() {
  return request<{ status: string; app_env: string; asr: string; tts: string }>('/readyz')
}

export function pingJava() {
  return request<PingData>('/api/v1/ping', undefined, JAVA_BASE)
}

/** 上传录音到 Python ASR（M1 为 stub；M2 接入 faster-whisper），DTO 类型来自生成契约 */
export async function asr(audioBlob: Blob, language = 'en') {
  const form = new FormData()
  form.append('audio', audioBlob, 'recording.webm')
  form.append('language', language)
  return request<AsrData>('/api/v1/asr', {
    method: 'POST',
    body: form,
  })
}
