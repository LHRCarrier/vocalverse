/**
 * 学习指标 API（docs/53 P2）：四指标看板 + 个人学习报表。
 *
 * 口径与聚合实现 = Python `app/insight/service.py`（docs/06 §9.1 修订）；
 * 管理端看板走控制台端点（`/api/v1/console/insight/overview`，Python 控制台令牌）。
 */
import { PYTHON_BASE, request } from './client'

export interface MetricValue {
  numerator: number
  denominator: number
  rate: number | null
}

export interface StatsOverview {
  period: { days: number; start: string; end: string }
  metrics: {
    ctr: MetricValue
    completion_rate: MetricValue & { units: Record<string, { total: number; done: number }> }
    interaction_rate: MetricValue & {
      sources: {
        trpg: { user: number; dm: number }
        defense: { answered: number; assigned: number }
      }
    }
    bounce_rate: MetricValue & { engaged_sessions: number }
  }
  trend: { date: string; events: number; page_views: number; sessions: number }[]
  dimensions: Record<string, { key: string; events: number }[]>
  notes: string[]
  generated_at: string
}

export interface LevelForecast {
  available: boolean
  model_version: string
  predicted_overall?: number
  current_avg?: number
  delta?: number
  direction?: 'up' | 'flat' | 'down'
  basis?: { attempts: number; slope: number; active_days: number; window_days: number }
  note?: string
  reason?: string
}

export interface StatsMe {
  period: { days: number; start: string; end: string }
  summary: {
    sessions: number
    attempts: number
    sing_attempts: number
    practice_minutes: number
    avg_overall: number | null
    best_overall: number | null
  }
  trend: { date: string; attempts: number; avg_overall: number | null; sing: number }[]
  radar: { axes: string[]; values: number[] }
  by_kind: { kind: string; count: number; avg_overall: number | null }[]
  forecast?: LevelForecast
  generated_at: string
}

export interface LearnModuleSummary {
  total?: number
  learning?: number
  events?: number
  page_views?: number
  pron?: number | null
  flu?: number | null
  gram?: number | null
  minutes?: number
  campaigns?: number
  summary: string
}

export interface LearnOverview {
  profile_line: string
  heatmap: { date: string; count: number; level: number }[]
  modules: Record<'words' | 'community' | 'speaking' | 'practice', LearnModuleSummary>
  generated_at: string
  forecast?: LevelForecast
}

export async function fetchLearnOverview(): Promise<LearnOverview> {
  const res = await request<LearnOverview>('/api/v1/stats/learn', undefined, PYTHON_BASE)
  return res.data
}

export interface LearnModuleDetail {
  key: string
  dims?: { pron: number | null; flu: number | null; gram: number | null }
  /** speaking = 三维按日趋势；community = 按日事件量（count） */
  trend?: {
    date: string
    pron?: number | null
    flu?: number | null
    gram?: number | null
    count?: number
  }[]
  weak_phonemes?: { phoneme: string; count: number; avg: number | null }[]
  minutes?: number
  by_kind?: { kind: string; count: number; minutes: number }[]
  campaigns?: { id: number; name: string; turns: number; user_turns: number; last_active_at: string | null }[]
  heatmap?: { date: string; count: number; level: number }[]
  items?: {
    word: string
    status: string
    scene: string
    created_at: string | null
    /** 词典首义（未收录为 null；docs/45 §6 词典子集） */
    translation?: string | null
    phonetic?: string | null
  }[]
  pages?: { page: string; count: number }[]
  events?: { event_type: string; count: number }[]
}

export async function fetchLearnModule(key: string, days = 30): Promise<LearnModuleDetail> {
  const res = await request<LearnModuleDetail>(
    `/api/v1/stats/learn/${key}?days=${days}`,
    undefined,
    PYTHON_BASE,
  )
  return res.data
}

/** XP/等级（docs/53 P5）：服务端聚合，前端不再写死初始 320 / 升级规则 */
export interface ProgressSummary {
  xp: number
  level: number
  title: string
  base: number
  next: number | null
  breakdown: Record<string, number>
  rules: { key: string; xp: number }[]
}

export async function fetchProgressSummary(): Promise<ProgressSummary> {
  const res = await request<ProgressSummary>('/api/v1/stats/progress', undefined, PYTHON_BASE)
  return res.data
}

export async function fetchStatsOverview(days = 30): Promise<StatsOverview> {
  const res = await request<StatsOverview>(`/api/v1/stats/overview?days=${days}`, undefined, PYTHON_BASE)
  return res.data
}

export async function fetchStatsMe(days = 30): Promise<StatsMe> {
  const res = await request<StatsMe>(`/api/v1/stats/me?days=${days}`, undefined, PYTHON_BASE)
  return res.data
}
