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
  generated_at: string
}

export async function fetchStatsOverview(days = 30): Promise<StatsOverview> {
  const res = await request<StatsOverview>(`/api/v1/stats/overview?days=${days}`, undefined, PYTHON_BASE)
  return res.data
}

export async function fetchStatsMe(days = 30): Promise<StatsMe> {
  const res = await request<StatsMe>(`/api/v1/stats/me?days=${days}`, undefined, PYTHON_BASE)
  return res.data
}
