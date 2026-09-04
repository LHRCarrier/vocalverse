/**
 * SSE 回合事件类型（docs/14 §3.3）—— 手写共享类型，**不进 gen:api**
 * （SSE 端点在 OpenAPI 无响应 schema，契约管线天然盲区，见 docs/16 A6）。
 * 与后端 `app/practice/events.py` 一一对应，改动须双端同步。
 */

export interface TurnStartEvent {
  type: 'turn_start'
  turn_index: number
  reference_text?: string | null
  question?: string | null
}

/** 用户 ASR 转写回显（2026-09-08 新增：聊天气泡展示用户说的话） */
export interface UserTranscriptEvent {
  type: 'user_transcript'
  turn_index: number
  text: string
}

export interface TextDeltaEvent {
  type: 'text_delta'
  text: string
}

export interface AudioChunkEvent {
  type: 'audio_chunk'
  url: string
}

export interface MetaBlockEvent {
  type: 'meta_block'
  grammar?: { score: number; errors: Array<{ word: string; fix: string }> } | null
  coach_note?: string | null
  corpus_hits: Array<{ phrase: string; state: 'ok' | 'fix' }>
  difficulty_delta: number
  conclude: boolean
  /** ③ 语义子分：内容相关度 {score,note}（LLM 判定，不进总分） */
  content?: { score?: number; note?: string } | null
  /** ③ 语义子分：词汇多样性 {score,note}（LLM 判定，不进总分） */
  vocab?: { score?: number; note?: string } | null
  /** defense：作答等级 green/yellow/red */
  level?: string | null
  /** defense：要点命中 {hits: string[], total: number} */
  hits?: { hits?: string[]; total?: number } | null
}

export interface ScoreDeltaEvent {
  type: 'score_delta'
  turn_index: number
  pronunciation?: number | null
  fluency?: number | null
  grammar?: number | null
}

export interface StreamErrorEvent {
  type: 'error'
  code: string
  recoverable: boolean
}

export interface TurnEndEvent {
  type: 'turn_end'
  turn_index: number
  score_status: 'ok' | 'pending' | 'unavailable'
}

export interface SessionEndEvent {
  type: 'session_end'
  summary?: string | null
  report_id?: number | null
  metrics: Record<string, unknown>
}

export type SseStreamEvent =
  | TurnStartEvent
  | UserTranscriptEvent
  | TextDeltaEvent
  | AudioChunkEvent
  | MetaBlockEvent
  | ScoreDeltaEvent
  | StreamErrorEvent
  | TurnEndEvent
  | SessionEndEvent
