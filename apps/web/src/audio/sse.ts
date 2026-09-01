/**
 * SSE 客户端 v2（docs/14 §3.3 / docs/16 A1）：
 * - `openSseFetch`：POST multipart 音频 + fetch ReadableStream 解析 SSE
 *   （EventSource 仅 GET，不能承载 POST 音频；本仓库无其他 GET 流消费方，统一替换）；
 * - 事件边界：`\n\n` 分隔、单事件可含多 `data:` 行（聚合）；`: ping` 心跳注释行忽略；
 * - AbortController 由调用方持有（组件卸载/跳转必须 abort，防连接泄漏）；
 * - 解析器为纯函数（`parseSseBuffer`），可单测（跨 chunk/多 data/未知事件）。
 */

import type { SseStreamEvent } from './sse-types'

export interface SseHandlers {
  onEvent?: (event: SseStreamEvent) => void
  onError?: (err: unknown) => void
  onClose?: () => void
}

/** 解析累积缓冲：返回 [消费后剩余缓冲, 已解析事件列表]。 */
export function parseSseBuffer(buffer: string): [string, SseStreamEvent[]] {
  const events: SseStreamEvent[] = []
  let idx: number
  while ((idx = buffer.indexOf('\n\n')) >= 0) {
    const block = buffer.slice(0, idx)
    buffer = buffer.slice(idx + 2)
    const dataLines: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith(':')) continue // 心跳/注释
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }
    if (dataLines.length === 0) continue
    const payload = dataLines.join('\n')
    try {
      const parsed = JSON.parse(payload) as SseStreamEvent
      if (parsed && typeof parsed === 'object' && 'type' in parsed) {
        events.push(parsed)
      }
    } catch {
      // 忽略坏块（容错）
    }
  }
  return [buffer, events]
}

export function openSseFetch(
  url: string,
  init: { method: string; body: FormData; headers?: HeadersInit },
  handlers: SseHandlers,
  signal?: AbortSignal,
): void {
  let buffer = ''
  const headers = { Accept: 'text/event-stream', ...(init.headers ?? {}) }
  fetch(url, { method: init.method, body: init.body, signal, headers })
    .then(async (resp) => {
      if (!resp.ok || !resp.body) {
        // 非 SSE 错误（409/429/413 等）：尝试读 JSON envelope
        const text = await resp.text()
        let message = `HTTP ${resp.status}`
        try {
          const body = JSON.parse(text) as { message?: string; code?: number }
          message = body.message ?? message
        } catch {
          /* keep default */
        }
        handlers.onError?.(new Error(message))
        handlers.onClose?.()
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const [rest, events] = parseSseBuffer(buffer)
        buffer = rest
        for (const event of events) {
          handlers.onEvent?.(event)
        }
      }
      handlers.onClose?.()
    })
    .catch((err) => {
      if ((err as Error).name === 'AbortError') return // 主动取消不算错误
      handlers.onError?.(err)
      handlers.onClose?.()
    })
}
