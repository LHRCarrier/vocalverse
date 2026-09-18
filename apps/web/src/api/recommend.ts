/**
 * 推荐 API（docs/06 §9.5）：推荐 feed + 水平预测趋势。
 * NOTE: M3 后端契约未落地，当前返回 mock；接线后改 request()。
 */
import { mockLevelForecast, mockRecommendations } from './mock/m3-data'
import type { LevelForecast, RecommendItem } from './m3-types'

const delay = (ms = 200) => new Promise<void>((r) => setTimeout(r, ms))

// TODO(契约): GET /api/v1/recommendations
export async function fetchRecommendations(): Promise<RecommendItem[]> {
  await delay()
  return mockRecommendations.map((r) => ({ ...r, tags: [...r.tags] }))
}

// TODO(契约): GET /api/v1/level-forecast
export async function fetchLevelForecast(): Promise<LevelForecast> {
  await delay()
  return {
    ...mockLevelForecast,
    dates: [...mockLevelForecast.dates],
    predicted: [...mockLevelForecast.predicted],
  }
}