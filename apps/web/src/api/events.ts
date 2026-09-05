/**
 * 埋点上报（docs/06 §9.1 / docs/14 §6.3）：10 类事件 + client_event_id 幂等去重。
 * 失败静默（埋点非关键路径）；每次生成唯一事件 id 防重复上报。
 */

let seq = 0

export type EventName =
  | 'page_view'
  | 'scene_start'
  | 'recording_start'
  | 'recording_complete'
  | 'score_event'
  | 'corpus_hit'
  | 'practice_complete'
  | 'fun_action'
  | 'free_chat_open'
  | 'free_chat_turn'
  | 'free_chat_switch'
  | 'free_chat_reset'
  | 'free_chat_rate'

export interface TrackOptions {
  page?: string
  targetType?: string
  targetId?: number
  sceneId?: number
  payload?: Record<string, unknown>
}

export async function track(name: EventName, options: TrackOptions = {}): Promise<void> {
  const clientEventId = `${Date.now()}-${(seq++).toString(36)}`
  try {
    const { request } = await import('@/api/client')
    await request('/api/v1/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event_type: name,
        client_event_id: clientEventId,
        occurred_at: Math.floor(Date.now() / 1000),
        page: options.page,
        target_type: options.targetType,
        target_id: options.targetId,
        scene_id: options.sceneId,
        payload: options.payload ?? {},
      }),
    })
  } catch {
    /* 静默 */
  }
}
