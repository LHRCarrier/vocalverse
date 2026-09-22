/**
 * 学习热力图网格（docs/53 P4）：学习主页与模块详情共用。
 * 接口按日返回 `[{date, count, level}]`（Python `app/insight/learn.py::_heatmap`）；
 * 无事件的日子前端补 level 0 —— 12 周 × 7 天网格（列 = 周，行 = 周一~周日，今天位于末列）。
 */

export interface HeatCell {
  date: Date
  level: 0 | 1 | 2 | 3
  /** 该日事件数（展示为 +N XP） */
  xp: number
}

export interface HeatDay {
  date: string
  count: number
  level: number
}

export function localDateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function buildHeatmapWeeks(days: HeatDay[] | undefined, weeks = 12): HeatCell[][] {
  const map = new Map<string, { count: number; level: 0 | 1 | 2 | 3 }>()
  for (const cell of days ?? []) {
    map.set(cell.date, { count: cell.count, level: cell.level as 0 | 1 | 2 | 3 })
  }
  const today = new Date()
  const monday = new Date(today)
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7))
  const start = new Date(monday)
  start.setDate(monday.getDate() - (weeks - 1) * 7)
  const cols: HeatCell[][] = []
  for (let w = 0; w < weeks; w++) {
    const col: HeatCell[] = []
    for (let d = 0; d < 7; d++) {
      const date = new Date(start)
      date.setDate(start.getDate() + w * 7 + d)
      const hit = map.get(localDateKey(date))
      col.push({ date, level: hit?.level ?? 0, xp: hit?.count ?? 0 })
    }
    cols.push(col)
  }
  return cols
}

export function isTodayCell(c: HeatCell): boolean {
  return c.date.toDateString() === new Date().toDateString()
}

export function isFutureCell(c: HeatCell): boolean {
  return c.date.getTime() > new Date().getTime()
}

export function heatCellKey(c: HeatCell): string {
  return localDateKey(c.date)
}
