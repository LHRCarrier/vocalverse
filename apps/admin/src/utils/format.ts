/** 展示格式化工具（控制台全局唯一来源，避免各页面各写一套） */

const DATE_TIME = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

/** ISO → `2026-09-10 12:00:00`（本地时区；后端出参一律带 offset） */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : DATE_TIME.format(d)
}

/** ISO → `09-10`（图表横轴用，省空间） */
export function fmtDayShort(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 秒 → `3天 4小时` / `12分 30秒`（服务 uptime 用） */
export function fmtDuration(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)} 秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分 ${Math.floor(seconds % 60)} 秒`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分`
  return `${Math.floor(seconds / 86400)} 天 ${Math.floor((seconds % 86400) / 3600)} 小时`
}

/** 毫秒 → `820ms` / `1.42s` */
export function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(2)}s`
}

/** 千分位整数 */
export function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return n.toLocaleString('zh-CN')
}

/** 大数缩写：12.3k / 4.5M（图表轴与统计块用） */
export function fmtCompact(n: number): string {
  const abs = Math.abs(n)
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(Math.round(n))
}

/** 0–1 比例 → `12.3%` */
export function fmtPercent(ratio: number | null | undefined, digits = 1): string {
  if (ratio === null || ratio === undefined) return '—'
  return `${(ratio * 100).toFixed(digits)}%`
}

/** 字节 → KiB/MiB */
export function fmtBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB']
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

/** 相对时间：`3 分钟前`（列表"最近"列用） */
export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return '—'
  const diff = Date.now() - t
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return `${Math.floor(diff / 86_400_000)} 天前`
}

/** 生成最近 N 天的 `[from, to)` ISO 区间（指标/趋势查询用） */
export function lastDaysRange(days: number): { from: string; to: string } {
  const to = new Date()
  const from = new Date(to.getTime() - days * 86_400_000)
  return { from: from.toISOString(), to: to.toISOString() }
}

/**
 * 依据时间跨度推荐聚合步长（秒）。
 * 服务端强制 `(to-from)/step ≤ 5000` 点（docs/50 §8.5），
 * 这里提前对齐，避免用户一选"90 天"就收到 46007。
 */
export function suggestStep(fromIso: string, toIso: string, targetPoints = 400): number {
  const span = (new Date(toIso).getTime() - new Date(fromIso).getTime()) / 1000
  const raw = span / targetPoints
  const steps = [60, 300, 600, 1800, 3600, 21600, 86400]
  return steps.find((s) => s >= raw) ?? 86400
}
