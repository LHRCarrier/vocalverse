/**
 * 媒体 API 域（社区 S3 · docs/47 §4.1）
 *
 * 三个要点：
 * 1. **URL 必须拼基址**：只有 JSON 请求会拼 `PYTHON_BASE`（client.ts），`<img>/<video>` 的
 *    `src` 不会 —— 打包壳里页面源是 `https://localhost`，相对路径会打到壳本身（404 + 混合内容拦截）。
 *    所有媒体地址一律过 `mediaUrl()`（docs/48 B5）。
 * 2. **上传走 XHR**：fetch 没有上传进度；这里用 XMLHttpRequest 拿 `upload.onprogress`。
 * 3. **错误体**：后端 Envelope `{code,message,data}`，非 2xx 时也要解析出 code/message。
 */
import { PYTHON_BASE, authHeaders } from './client'

export type MediaKind = 'image' | 'video' | 'avatar'

export interface MediaAssetView {
  id: string
  url: string
  kind: MediaKind
  mimeType: string
  size: number
  width: number | null
  height: number | null
  durationS: number | null
}

export interface UploadOptions {
  width?: number
  height?: number
  durationS?: number
  /** 上传进度回调（0..1） */
  onProgress?: (ratio: number) => void
  signal?: AbortSignal
}

export class MediaUploadError extends Error {
  constructor(
    public readonly code: number,
    message: string,
    public readonly httpStatus: number,
  ) {
    super(message)
  }
}

/** 媒体地址 → 可直接给 `<img>/<video>` 用的绝对/代理地址（幂等） */
export function mediaUrl(path: string | null | undefined): string {
  if (!path) return ''
  if (/^(https?:|blob:|data:)/i.test(path)) return path
  return `${PYTHON_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

/** 上传单个媒体（图片/视频/头像） */
export function uploadMedia(
  file: File,
  kind: MediaKind,
  opts: UploadOptions = {},
): Promise<MediaAssetView> {
  return new Promise<MediaAssetView>((resolve, reject) => {
    const form = new FormData()
    form.append('file', file, file.name)
    form.append('kind', kind)
    if (opts.width) form.append('width', String(Math.round(opts.width)))
    if (opts.height) form.append('height', String(Math.round(opts.height)))
    if (opts.durationS) form.append('duration_s', String(opts.durationS))

    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${PYTHON_BASE}/api/v1/media`)
    const headers = authHeaders() as Record<string, string>
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v)

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && opts.onProgress) opts.onProgress(e.loaded / e.total)
    }
    xhr.onerror = () => reject(new MediaUploadError(-1, '网络异常，上传失败', 0))
    xhr.ontimeout = () => reject(new MediaUploadError(-1, '上传超时，请重试', 0))
    xhr.onabort = () => reject(new MediaUploadError(-1, '已取消上传', 0))
    xhr.onload = () => {
      let body: { code?: number; message?: string; data?: MediaAssetView } | null = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        body = null
      }
      if (xhr.status >= 200 && xhr.status < 300 && body?.code === 0 && body.data) {
        resolve(body.data)
        return
      }
      reject(
        new MediaUploadError(
          body?.code ?? -1,
          body?.message || `上传失败（HTTP ${xhr.status}）`,
          xhr.status,
        ),
      )
    }
    if (opts.signal) {
      opts.signal.addEventListener('abort', () => xhr.abort(), { once: true })
    }
    xhr.send(form)
  })
}

/** 删除自己的媒体（软删；帖子里的引用会变成 40403 占位） */
export async function deleteMedia(id: string): Promise<void> {
  const resp = await fetch(`${PYTHON_BASE}/api/v1/media/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!resp.ok) {
    let msg = `删除失败（HTTP ${resp.status}）`
    try {
      const body = (await resp.json()) as { message?: string }
      if (body.message) msg = body.message
    } catch {
      /* 非 JSON 错误体：用默认文案 */
    }
    throw new MediaUploadError(-1, msg, resp.status)
  }
}

/** 我的上传列表（配额排查用） */
export async function fetchMyMedia(limit = 20): Promise<MediaAssetView[]> {
  const resp = await fetch(`${PYTHON_BASE}/api/v1/media?limit=${limit}`, {
    headers: authHeaders(),
  })
  if (!resp.ok) return []
  const body = (await resp.json()) as { data?: { items?: MediaAssetView[] } }
  return body.data?.items ?? []
}

/** 前端预校验（与后端同口径，失败不进上传队列） */
export function precheck(file: File, kind: MediaKind): string | null {
  const isVideo = kind === 'video'
  const max = isVideo ? 64 * 1024 * 1024 : 20 * 1024 * 1024
  if (file.size <= 0) return '文件为空'
  if (file.size > max) return isVideo ? '视频超过 64MB' : '图片超过 20MB'
  const ok = isVideo
    ? ['video/mp4', 'video/webm']
    : ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
  // 部分安卓 WebView 的 file.type 为空 → 不拦，交给服务端魔数嗅探判定
  if (file.type && !ok.includes(file.type)) return isVideo ? '仅支持 MP4 / WebM' : '仅支持 JPG/PNG/WebP/GIF'
  return null
}
