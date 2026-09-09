/**
 * 唱吧 API 封装（M3 唱歌 P0 D7）：歌曲列表/详情 + 整首上传 + 任务轮询/结果。
 * 错误码语义见 docs/api/error-codes.md（40905 参考旋律未就绪 / 41302 超 180s / 40002 音频过短）。
 */
import { ApiError, request } from './client'

export interface SongSummary {
  id: number
  title: string
  artist?: string | null
  level: number
  duration_s?: number | null
  bpm?: number | null
  musical_key?: string | null
  cover_url?: string | null
  /** 参考旋律音频（共享卷路径；前端取 basename 走 /api/v1/audio/{name} 回放） */
  audio_url?: string | null
  pitch_ref_status: 'missing' | 'building' | 'ready' | 'invalid'
  expected_lines: number
}

export interface SongLine {
  seq: number
  start_ms: number
  end_ms?: number | null
  text: string
  pitch_ref: { f0s?: number[]; notes?: (string | null)[]; midi?: (number | null)[] }
}

export interface SongDetail extends SongSummary {
  lines: SongLine[]
}

export interface SingSessionCreated {
  id: number
  kind: string
  song_id?: number | null
  assigned_turns?: number | null
}

export interface SingAttemptStatus {
  attempt_id: number
  status: 'queued' | 'processing' | 'done' | 'failed'
  progress: { done_lines: number; total: number }
  error?: string | null
}

export interface SingLineResult {
  seq: number
  start_ms: number
  end_ms: number
  pitch_score: number | null
  rhythm_score: number | null
  pron_score: number | null
  synced: boolean
  skipped: boolean
  reason?: string | null
  ref_seq?: number | null
  no_ref?: boolean
  /** v2：该句起唱偏差 ms（相对「LRC 时间戳 + 整首对齐偏移」；null=未检出） */
  onset_dev_ms?: number | null
  /** D4：用户逐帧 F0 [[t_ms, f0_hz], ...] */
  user_f0: [number, number][]
  /** 帧级折叠 cent 偏差（D3 图辅助） */
  cent_dev?: number[]
}

export interface SingAttemptResult {
  id: number
  song_id: number
  audio_url?: string | null
  duration_s: number
  overall: number | null
  pitch: number | null
  rhythm: number | null
  pron: number | null
  is_complete: boolean
  expected_lines: number
  scoring_version: string
  ref_version?: string | null
  lines: SingLineResult[]
  alignment: { bpm_ratio?: number; offset_ms?: number; method?: string; version?: string }
  created_at?: string | null
}

export async function fetchSongs(): Promise<SongSummary[]> {
  const resp = await request<SongSummary[]>('/api/v1/songs')
  return resp.data
}

export async function fetchSongDetail(songId: number): Promise<SongDetail> {
  const resp = await request<SongDetail>(`/api/v1/songs/${songId}`)
  return resp.data
}

export async function createSingSession(songId: number): Promise<SingSessionCreated> {
  const resp = await request<SingSessionCreated>('/api/v1/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind: 'sing', song_id: songId }),
  })
  return resp.data
}

export async function uploadSingAudio(sessionId: number, blob: Blob): Promise<SingAttemptStatus> {
  const form = new FormData()
  form.append('audio', blob, 'sing.webm')
  const resp = await request<SingAttemptStatus>(`/api/v1/sessions/${sessionId}/audio`, {
    method: 'POST',
    body: form,
  })
  return resp.data
}

export async function fetchSingStatus(attemptId: number): Promise<SingAttemptStatus> {
  const resp = await request<SingAttemptStatus>(`/api/v1/sing/attempts/${attemptId}/status`)
  return resp.data
}

export async function fetchSingResult(attemptId: number): Promise<SingAttemptResult> {
  const resp = await request<SingAttemptResult>(`/api/v1/sing/attempts/${attemptId}`)
  return resp.data
}

/** ApiError → 可读提示（40905/41302/40002/42901 等错误码文案映射） */
export function singErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case 40905:
        return '参考旋律生成中或缺失，稍后再试（提示：等提取完成即可跟唱）'
      case 41302:
        return '录音超过 3 分钟上限，请重唱一遍完整的歌'
      case 40002:
        return '录音太短或为空，请重录'
      case 42901:
        return '今日跟唱次数已达上限（每小时 5 次），稍后再试'
      default:
        return err.message
    }
  }
  return err instanceof Error ? err.message : '请求失败，请重试'
}
