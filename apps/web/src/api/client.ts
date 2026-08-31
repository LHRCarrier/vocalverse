/**
 * API 客户端 —— 统一 envelope 解析（docs/06 第 7 章：{code, message, data}）
 *
 * - 语音/LLM 热路径：Python 8000（dev 下走 Vite 代理 /api/v1）
 * - 管理端/JWT：Java 8080（dev 下走 /manage 代理）
 */

export interface Envelope<T> {
  code: number
  message: string
  data: T
}

const PYTHON_BASE = import.meta.env.VITE_PYTHON_BASE ?? ''
const JAVA_BASE = import.meta.env.VITE_JAVA_BASE ?? '/manage'

export class ApiError extends Error {
  constructor(
    public readonly code: number,
    message: string,
    public readonly httpStatus: number,
  ) {
    super(message)
  }
}

export async function request<T>(path: string, init?: RequestInit, base = PYTHON_BASE): Promise<Envelope<T>> {
  const resp = await fetch(`${base}${path}`, init)
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
  return request<{ service: string; status: string }>('/api/v1/ping', undefined, JAVA_BASE)
}

/** 上传录音到 Python ASR（M1 为 stub；M2 接入 faster-whisper） */
export async function asr(audioBlob: Blob, language = 'en') {
  const form = new FormData()
  form.append('audio', audioBlob, 'recording.webm')
  form.append('language', language)
  return request<{ text: string; language: string; confidence: number }>('/api/v1/asr', {
    method: 'POST',
    body: form,
  })
}
