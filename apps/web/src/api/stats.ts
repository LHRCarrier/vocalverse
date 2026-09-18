/**
 * 报表 API（docs/06 §9.1）：四指标 + 口语/唱歌趋势 + 雷达。
 * NOTE: M3 后端契约未落地，当前返回 mock；接线后改 request()。
 */
import { mockStats } from './mock/m3-data'
import type { MetricBoard, StatRadar, StatTrend } from './m3-types'

const delay = (ms = 200) => new Promise<void>((r) => setTimeout(r, ms))

// TODO(契约): GET /api/v1/stats/overview
export async function fetchStatsOverview(): Promise<{ metrics: MetricBoard }> {
  await delay()
  return { metrics: { ...mockStats.metrics } }
}

// TODO(契约): GET /api/v1/stats/trend
export async function fetchTrend(scope: 'oral' | 'sing'): Promise<StatTrend> {
  await delay()
  return cloneTrend(scope === 'oral' ? mockStats.oralTrend : mockStats.singTrend)
}

// TODO(契约): GET /api/v1/stats/radar
export async function fetchRadar(scope: 'oral' | 'sing'): Promise<StatRadar> {
  await delay()
  const r = scope === 'oral' ? mockStats.oralRadar : mockStats.singRadar
  return { dimensions: [...r.dimensions], values: [...r.values] }
}

function cloneTrend(t: StatTrend): StatTrend {
  return { dates: [...t.dates], series: t.series.map((s) => ({ name: s.name, values: [...s.values] })) }
}