/**
 * 唱吧 API 封装（M3 唱歌 P0 D7）：歌曲列表/详情 + 整首上传 + 任务轮询/结果。
 * 错误码语义见 docs/api/error-codes.md（40905 参考旋律未就绪 / 41302 超 180s / 40002 音频过短）。
 *
 * **DTO 来自契约生成**（2026-09-10 · 拷问报告 P1-14 修复）：后端这些端点此前无 `response_model`
 * → OpenAPI 里是空 schema → 前端只能手写 DTO 副本，契约漂移无人拦（实测 `alignment.bpm_source`
 * 手写成 `'onset' | 'duration'`，后端实际 `onset-f0|onset-flux|onset-arbitrated|duration`）。
 * 现后端补 `SingAlignment`/`AttemptResult` 等具名模型，类型统一取
 * `src/api/generated/python-api.d.ts`（`pnpm gen:api` 生成，入库），本文件只做**别名导出**——
 * 后端改字段后跑生成即在前端 typecheck 暴露断点，不再维护第二份字段表。
 */
import { ApiError, request } from './client'
import type { components } from './generated/python-api'

type Schemas = components['schemas']

export type SongSummary = Schemas['SongSummary']
export type SongLine = Schemas['SongLine']
export type SongDetail = Schemas['SongDetail']
/** 收藏切换结果（PUT=收藏 / DELETE=取消，均幂等） */
export type SongFavoriteResult = Schemas['FavoriteState']
/** 上传受理回执（**只有 attempt_id/status**，进度靠 status 端点轮询） */
export type SingSubmitAck = Schemas['SubmitAck']
export type SingAttemptStatus = Schemas['AttemptStatus']
export type SingAlignment = Schemas['SingAlignment']
export type SingLineResult = Schemas['ScoreLine']
export type SingAttemptResult = Schemas['AttemptResult']

/**
 * `POST /api/v1/sessions` 尚未补 `response_model`（契约快照里该 op 的 `data` 仍是 `Any`），
 * 故这里保留手写形状；后端补齐后应改为生成类型别名（与上面 7 个同规格）。
 */
export interface SingSessionCreated {
  id: number
  kind: string
  song_id?: number | null
  assigned_turns?: number | null
}

export async function fetchSongs(): Promise<SongSummary[]> {
  const resp = await request<SongSummary[]>('/api/v1/songs')
  return resp.data
}

export async function fetchSongDetail(songId: number): Promise<SongDetail> {
  const resp = await request<SongDetail>(`/api/v1/songs/${songId}`)
  return resp.data
}

/**
 * 收藏（favorited=true → PUT）/ 取消收藏（false → DELETE）——同一按钮再点即取消。
 * 后端幂等：重复收藏不报错、未收藏时取消也返回成功；歌曲不存在/未发布 → 40401。
 */
export async function setSongFavorite(
  songId: number,
  favorited: boolean,
): Promise<SongFavoriteResult> {
  const resp = await request<SongFavoriteResult>(`/api/v1/songs/${songId}/favorite`, {
    method: favorited ? 'PUT' : 'DELETE',
  })
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

export async function uploadSingAudio(sessionId: number, blob: Blob): Promise<SingSubmitAck> {
  const form = new FormData()
  form.append('audio', blob, 'sing.webm')
  const resp = await request<SingSubmitAck>(`/api/v1/sessions/${sessionId}/audio`, {
    method: 'POST',
    body: form,
  })
  return resp.data
}

export async function fetchSingStatus(
  attemptId: number,
  signal?: AbortSignal,
): Promise<SingAttemptStatus> {
  const resp = await request<SingAttemptStatus>(`/api/v1/sing/attempts/${attemptId}/status`, {
    signal,
  })
  return resp.data
}

export async function fetchSingResult(
  attemptId: number,
  signal?: AbortSignal,
): Promise<SingAttemptResult> {
  const resp = await request<SingAttemptResult>(`/api/v1/sing/attempts/${attemptId}`, { signal })
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
      case 50003:
        return '评分失败：算法侧异常（已记录），可重试或反馈'
      case 50002:
        return '服务暂时异常，请稍后重试'
      default:
        return err.message
    }
  }
  return err instanceof Error ? err.message : '请求失败，请重试'
}

/**
 * 任务态失败文案（P0-5，2026-09-10）：**优先按后端回带的 `code` 映射**，其次才用服务端文案。
 * 后端自 2026-09-10 起在失败任务态回带 `code`（50003 算法失败 / 50002 服务内部错误），
 * 因此前端不再依赖 message 字符串匹配（docs/api/error-codes.md:30-31、docs/21 §3.6）。
 */
export function singFailureMessage(s: {
  code?: number | null
  error?: string | null
}): string {
  if (s.code === 50003) return '评分失败：算法侧异常（已记录），可重试或反馈'
  if (s.code === 50002) return '服务暂时异常，请稍后重试'
  return s.error || '评分失败，请重试'
}

/**
 * 收藏失败文案：**按 HTTP 状态区分原因**，不再把所有失败压成一句「请重试」。
 * 2026-09-10 实测踩坑：后端容器未重建（无收藏路由 → 404）时，前端只显示「收藏操作失败，请重试」，
 * 排查要靠翻容器日志；现在 404/401/5xx 各自给出可执行的下一步。
 */
export function favoriteErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.httpStatus === 404)
      return '收藏失败：服务端没有收藏接口（后端需重建/重启到最新版本）'
    if (err.httpStatus === 401) return '收藏失败：登录已过期，请重新登录'
    if (err.httpStatus >= 500)
      return '收藏失败：服务端内部错误（若刚上线该功能，请确认已执行迁移 0011）'
  }
  return '收藏操作失败，请重试'
}
