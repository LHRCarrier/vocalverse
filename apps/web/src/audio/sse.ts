/**
 * SSE 客户端（docs/06 第 8 章：服务端→前端单向流；音频为时间轴权威、文本为字幕）。
 *
 * 事件协议（M2 与 Python Streamer 对齐）：
 *   text_delta:  { type: "text_delta", text: string }
 *   audio_chunk: { type: "audio_chunk", url: string }   // 或 base64
 *   done:        { type: "done" }
 */

export type SseEvent =
  | { type: 'text_delta'; text: string }
  | { type: 'audio_chunk'; url: string }
  | { type: 'done' }

export function openSse(
  url: string,
  handlers: {
    onEvent?: (event: SseEvent) => void
    onError?: (err: unknown) => void
    onClose?: () => void
  },
): () => void {
  const es = new EventSource(url)
  es.onmessage = (e: MessageEvent<string>) => {
    try {
      const parsed = JSON.parse(e.data) as SseEvent
      handlers.onEvent?.(parsed)
      if (parsed.type === 'done') {
        es.close()
        handlers.onClose?.()
      }
    } catch (err) {
      handlers.onError?.(err)
    }
  }
  es.onerror = (err) => {
    handlers.onError?.(err)
    es.close()
    handlers.onClose?.()
  }
  return () => es.close()
}
