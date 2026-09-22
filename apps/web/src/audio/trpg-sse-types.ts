/**
 * 酒馆（TRPG 跑团）SSE 事件类型 —— 手写镜像，**不进 gen:api**
 * （与后端 `services/python/app/trpg/events.py` 一一对应，改动须双端同步）。
 *
 * 与练习域 SseStreamEvent 分离：酒馆有 trpg_ready / status / system（系统卡），
 * 无 turn_index/评分语义；序列化同为单行 JSON + `data:` 前缀。
 */

export interface TrpgReadyEvent {
  type: 'trpg_ready'
  campaign_id: number
  campaign_name: string
  is_first: boolean
}

export interface TrpgUserTranscriptEvent {
  type: 'user_transcript'
  text: string
  audio_url?: string | null
  words?: Array<{ word: string; start: number; end: number; [key: string]: unknown }> | null
}

export interface TrpgTextDeltaEvent {
  type: 'text_delta'
  text: string
}

/** 工具执行状态：rolling=掷骰判定中 / scene=切换场景中 */
export interface TrpgStatusEvent {
  type: 'status'
  stage: string
}

export interface TrpgAudioChunkEvent {
  type: 'audio_chunk'
  url: string
  duration?: number | null
  /** 本句原文（卡拉OK逐词高亮定位用；2026-09-21 加） */
  text?: string | null
  /** 本句在 DM 整段内容里的字符偏移 */
  offset?: number | null
}

/** 系统卡（开场/过场/判定）——与 trpg_messages.kind=system 同协议 */
export interface TrpgSystemCardEvent {
  type: 'system'
  trpg_sys: 'open' | 'scene' | 'dice'
  payload: Record<string, unknown>
}

export interface TrpgTurnEndEvent {
  type: 'turn_end'
  message_id: number
  usage?: Record<string, unknown> | null
}

export interface TrpgStreamErrorEvent {
  type: 'error'
  code: string
  recoverable: boolean
}

export type TrpgSseEvent =
  | TrpgReadyEvent
  | TrpgUserTranscriptEvent
  | TrpgTextDeltaEvent
  | TrpgStatusEvent
  | TrpgAudioChunkEvent
  | TrpgSystemCardEvent
  | TrpgTurnEndEvent
  | TrpgStreamErrorEvent
